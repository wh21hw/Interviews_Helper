from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

from . import __version__
from .browser import crawl, prepare_manual_login
from .config import DATA_DIR, DEFAULT_OUTPUT, DEFAULT_PROFILE, DEFAULT_PROFILE_ROOT, RUN_DIR
from .platforms.public import public_profile_key
from .retrieval import hybrid_search
from .service import build_library, generate_keywords, load_library
from .storage.checkpoint import RunCheckpoint


def _common_paths(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--seed", type=Path, help="可选的已核验种子 JSON")
    parser.add_argument("--database", type=Path, default=DATA_DIR / "interviews.sqlite3")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="interviews-helper",
        description="面向 Agent 的可追溯面经库构建与混合检索工具",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    collect = commands.add_parser("collect", help="按岗位采集并重建题库")
    collect.add_argument("--job", required=True, help="目标岗位，例如 后端开发工程师")
    collect.add_argument("--keywords", default="", help="覆盖自动生成的关键词，逗号分隔")
    collect.add_argument("--url-file", type=Path, help="补充公开页面 URL，每行一个")
    collect.add_argument("--limit", type=int, default=3, help="每个关键词最多读取的笔记数")
    collect.add_argument("--delay", type=float, default=15.0, help="页面操作间隔秒数")
    collect.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    collect.add_argument("--profile-root", type=Path, default=DEFAULT_PROFILE_ROOT)
    collect.add_argument("--manual-login-wait", type=int, default=300)
    collect.add_argument("--proxy", default=os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY"))
    collect.add_argument("--backend", choices=("cdp", "persistent"), default="cdp")
    collect.add_argument("--cdp-port", type=int, default=9222)
    collect.add_argument("--no-ocr", dest="enable_ocr", action="store_false")
    collect.add_argument("--ocr-max-images", type=int, default=9)
    collect.add_argument("--run-id", help="指定运行 ID；用于精确恢复某次任务")
    collect.add_argument("--no-resume", dest="resume", action="store_false", help="创建新任务")
    collect.set_defaults(enable_ocr=True, resume=True)
    _common_paths(collect)

    build = commands.add_parser("build", help="从已落盘快照离线重建题库")
    _common_paths(build)

    search = commands.add_parser("search", help="使用 grep 与本地向量混合召回")
    search.add_argument("query", help="自然语言检索词")
    search.add_argument("--database", type=Path, default=DATA_DIR / "interviews.sqlite3")
    search.add_argument("--grep", dest="grep_pattern", help="额外的正则过滤/召回表达式")
    search.add_argument("--top-k", type=int, default=20)
    search.add_argument("--encoder", choices=("hashing", "sentence-transformers"), default="hashing")
    search.add_argument("--model", default="BAAI/bge-small-zh-v1.5",
                        help="sentence-transformers 模型名或本地路径")
    search.add_argument("--json", action="store_true", help="输出适合 Agent 消费的 JSON")

    login = commands.add_parser("login", help="打开平台页面，由用户手动登录")
    login.add_argument("platform", choices=("xhs", "nowcoder", "zhihu", "weixin"))
    login.add_argument("--profile-root", type=Path, default=DEFAULT_PROFILE_ROOT)
    login.add_argument("--proxy", default=os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY"))
    login.add_argument("--cdp-port", type=int, default=9222)
    login.add_argument("--wait", type=int, default=600)

    status = commands.add_parser("status", help="查看最近的采集断点")
    status.add_argument("--json", action="store_true")
    return parser


def _read_urls(path: Path | None) -> list[str]:
    if not path:
        return []
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")]


def _collect(args: argparse.Namespace) -> int:
    keywords = generate_keywords(args.job, args.keywords)
    urls = _read_urls(args.url_file)
    spec = {"job": args.job, "keywords": keywords, "urls": urls, "limit": args.limit,
            "ocr": args.enable_ocr, "ocr_max_images": args.ocr_max_images}
    checkpoint = RunCheckpoint.open(spec, run_id=args.run_id, resume=args.resume)
    print(f"运行 ID：{checkpoint.run_id}；状态文件：{checkpoint.path}")
    posts = load_library(args.seed)
    excluded = {urlparse(post.url).path.rsplit("/", 1)[-1] for post in posts
                if post.platform == "小红书" and "/explore/" in urlparse(post.url).path}
    try:
        posts.extend(crawl(
            keywords, [], max(1, args.limit), max(3.0, args.delay), args.profile,
            args.proxy, args.backend, args.cdp_port, args.enable_ocr,
            max(0, args.ocr_max_images), excluded, max(30, args.manual_login_wait), checkpoint,
        ))
        if all(checkpoint.is_done(f"xhs:keyword:{keyword}") for keyword in keywords):
            checkpoint.mark_done("xhs:session")
    except Exception as exc:
        checkpoint.mark_failed("xhs:session", exc)
        print(f"小红书采集未完成：{exc}", file=sys.stderr)
    groups: dict[str, list[str]] = {}
    for url in urls:
        groups.setdefault(public_profile_key(url), []).append(url)
    for key, group in groups.items():
        try:
            posts.extend(crawl(
                [], group, 1, max(3.0, args.delay), args.profile_root / f".browser-profile-{key}",
                args.proxy, args.backend, args.cdp_port, args.enable_ocr,
                max(0, args.ocr_max_images), set(), max(30, args.manual_login_wait), checkpoint,
            ))
            if all(checkpoint.is_done(f"web:url:{url.split('#', 1)[0]}") for url in group):
                checkpoint.mark_done(f"{key}:session")
        except Exception as exc:
            checkpoint.mark_failed(f"{key}:session", exc)
            print(f"{key} 采集未完成：{exc}", file=sys.stderr)
    posts.extend(load_library(None))
    posts, questions = build_library(posts, args.database, args.output)
    checkpoint.finish()
    print(json.dumps({"run_id": checkpoint.run_id, "status": checkpoint.state["status"],
                      "sources": len(posts), "questions": len(questions),
                      "database": str(args.database.resolve()), "html": str(args.output.resolve())},
                     ensure_ascii=False))
    return 0


def _status(as_json: bool) -> int:
    records = []
    for path in sorted(RUN_DIR.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)[:20]:
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
            records.append({key: state.get(key) for key in
                            ("run_id", "status", "updated_at", "completed_items", "failures", "spec")})
        except (OSError, json.JSONDecodeError):
            continue
    if as_json:
        print(json.dumps(records, ensure_ascii=False, indent=2))
    else:
        for item in records:
            print(f"{item['run_id']}  {item['status']}  {item['updated_at']}  "
                  f"completed={len(item['completed_items'] or [])} failures={len(item['failures'] or {})}")
    return 0


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    args = make_parser().parse_args(argv)
    if args.command == "collect":
        return _collect(args)
    if args.command == "build":
        posts, questions = build_library(load_library(args.seed), args.database, args.output)
        print(json.dumps({"sources": len(posts), "questions": len(questions),
                          "database": str(args.database.resolve()), "html": str(args.output.resolve())},
                         ensure_ascii=False))
        return 0
    if args.command == "search":
        results = hybrid_search(args.query, args.database, top_k=args.top_k,
                                grep_pattern=args.grep_pattern, encoder=args.encoder,
                                model_name=args.model)
        if args.json:
            print(json.dumps({"query": args.query, "count": len(results), "results": results},
                             ensure_ascii=False, indent=2))
        else:
            for index, item in enumerate(results, 1):
                print(f"{index:>2}. [{item['topic']}] {item['question']}  score={item['score']:.5f}")
        return 0
    if args.command == "login":
        profile = (DEFAULT_PROFILE if args.platform == "xhs"
                   else args.profile_root / f".browser-profile-{args.platform}")
        prepare_manual_login(args.platform, profile, args.proxy, args.cdp_port, max(30, args.wait))
        return 0
    return _status(args.json)


if __name__ == "__main__":
    raise SystemExit(main())

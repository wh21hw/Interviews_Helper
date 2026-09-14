from __future__ import annotations
import hashlib
import json
import os
import sqlite3
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, urlunparse
from ..config import RAW_DIR
from ..models import Post


def load_seed(path: Path) -> list[Post]:
    posts = [Post(**item) for item in json.loads(path.read_text(encoding="utf-8"))]
    for post in posts:
        if "搜索索引" in post.platform:
            post.source_type = "indexed"
            post.is_complete = False
    return posts


def save_posts(posts: list[Post], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([asdict(p) for p in posts], ensure_ascii=False, indent=2), encoding="utf-8")


def load_raw_posts() -> list[Post]:
    posts: list[Post] = []
    if not RAW_DIR.exists():
        return posts
    for path in RAW_DIR.glob("*.json"):
        try:
            posts.append(Post(**json.loads(path.read_text(encoding="utf-8"))))
        except Exception as exc:
            print(f"跳过损坏的原始快照 {path.name}：{exc}")
    return posts


def persist_raw(post: Post) -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha1(post_identity(post).encode("utf-8")).hexdigest()[:12]
    (RAW_DIR / f"{post.platform}_{digest}.json").write_text(
        json.dumps(asdict(post), ensure_ascii=False, indent=2), encoding="utf-8"
    )


def post_identity(post: Post) -> str:
    """为同一来源生成稳定标识；登录通知和跟踪参数不参与去重。"""
    parsed = urlparse(post.url)
    known_hosts = ("xiaohongshu.com", "nowcoder.com", "zhihu.com", "weixin.qq.com")
    if any(host in parsed.netloc.lower() for host in known_hosts):
        canonical = urlunparse((parsed.scheme.lower() or "https", parsed.netloc.lower(),
                                parsed.path.rstrip("/"), "", "", ""))
        return f"{post.platform}:{canonical}"
    return f"{post.platform}:{post.url}#{post.title}"


def save_database(posts: list[Post], questions: list[dict], path: Path) -> None:
    """原子重建规范化 SQLite 索引；JSON 原始文件仍作为可审计输入保留。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    if temp_path.exists():
        temp_path.unlink()
    connection = sqlite3.connect(temp_path)
    try:
        connection.executescript("""
            PRAGMA foreign_keys = ON;
            CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE posts (
                source_id TEXT PRIMARY KEY, platform TEXT NOT NULL, title TEXT NOT NULL,
                url TEXT NOT NULL, text TEXT NOT NULL, company TEXT, business TEXT, date TEXT,
                confidence TEXT, keyword TEXT, collected_at TEXT, source_type TEXT,
                collection_depth TEXT, expected_image_count INTEGER, downloaded_image_count INTEGER,
                ocr_page_count INTEGER, is_complete INTEGER
            );
            CREATE TABLE questions (
                question_id TEXT PRIMARY KEY, question TEXT NOT NULL, normalized TEXT NOT NULL UNIQUE,
                topic TEXT, frequency INTEGER NOT NULL, confidence TEXT, quality_score REAL NOT NULL,
                companies_json TEXT NOT NULL, platforms_json TEXT NOT NULL, businesses_json TEXT NOT NULL
            );
            CREATE TABLE question_sources (
                question_id TEXT NOT NULL REFERENCES questions(question_id) ON DELETE CASCADE,
                source_id TEXT NOT NULL REFERENCES posts(source_id) ON DELETE CASCADE,
                evidence_type TEXT, evidence_page INTEGER, evidence_line INTEGER, evidence_excerpt TEXT,
                PRIMARY KEY (question_id, source_id)
            );
            CREATE INDEX idx_posts_company ON posts(company);
            CREATE INDEX idx_posts_date ON posts(date);
            CREATE INDEX idx_questions_topic ON questions(topic);
        """)
        connection.executemany("INSERT INTO meta(key,value) VALUES(?,?)", [
            ("schema_version", "1"), ("generated_at", datetime.now().isoformat(timespec="seconds")),
        ])
        for post in posts:
            source_id = hashlib.sha1(post_identity(post).encode("utf-8")).hexdigest()[:16]
            connection.execute(
                "INSERT INTO posts VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (source_id, post.platform, post.title, post.url, post.text, post.company, post.business,
                 post.date, post.confidence, post.keyword, post.collected_at, post.source_type,
                 post.collection_depth, post.expected_image_count, post.downloaded_image_count,
                 post.ocr_page_count, int(post.is_complete)),
            )
        for item in questions:
            question_id = hashlib.sha1(item["normalized"].encode("utf-8")).hexdigest()[:16]
            connection.execute(
                "INSERT INTO questions VALUES(?,?,?,?,?,?,?,?,?,?)",
                (question_id, item["question"], item["normalized"], item["topic"], item["frequency"],
                 item["confidence"], item["quality_score"], json.dumps(item["companies"], ensure_ascii=False),
                 json.dumps(item["platforms"], ensure_ascii=False),
                 json.dumps(item["businesses"], ensure_ascii=False)),
            )
            for source in item["sources"]:
                evidence = source.get("evidence", {})
                connection.execute(
                    "INSERT OR IGNORE INTO question_sources VALUES(?,?,?,?,?,?)",
                    (question_id, source["source_id"], evidence.get("type"), evidence.get("page"),
                     evidence.get("line"), evidence.get("excerpt", "")),
                )
        connection.commit()
    finally:
        connection.close()
    os.replace(temp_path, path)

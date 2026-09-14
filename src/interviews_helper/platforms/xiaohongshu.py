from __future__ import annotations
import re
import time
from typing import Any
from urllib.parse import quote, urlencode, urlparse
from ..config import IMAGE_DIR
from ..models import Post
from ..pipeline.questions import clean_text, infer_company, split_questions
from ..runtime import page_blocked, save_block_evidence
from ..storage.repository import persist_raw


def extract_xhs_note_text(body: str, card_title: str, description: str) -> str:
    """从详情页正文中截取笔记主体，排除首页推荐流、评论和页脚。"""
    lines = [clean_text(line) for line in (body or "").splitlines()]
    title = clean_text(card_title)
    starts = [idx for idx, line in enumerate(lines) if title and line == title]
    if starts:
        # 页面前部推荐卡片也可能出现同名标题，详情主体通常是最后一次出现。
        start = starts[-1]
        end = len(lines)
        for idx in range(start + 1, len(lines)):
            line = lines[idx]
            if line == "猜你想搜" or re.fullmatch(r"共\s*\d+\s*条评论", line):
                end = idx
                break
        main_text = clean_text("\n".join(lines[start:end]))
        if len(main_text) >= 20:
            return main_text
    return clean_text(description) if len(clean_text(description)) >= 40 else clean_text(body)


def xhs_image_urls(note_card: dict) -> list[str]:
    """从搜索结果卡片中提取每张图片的一个可用 CDN 地址。"""
    urls: list[str] = []
    for image in note_card.get("image_list", []) or []:
        if not isinstance(image, dict):
            continue
        candidates = [image.get("url_default"), image.get("url_pre"), image.get("url")]
        for info in image.get("info_list", []) or []:
            if isinstance(info, dict):
                candidates.append(info.get("url"))
        url = next((value for value in candidates if isinstance(value, str) and value.startswith("http")), "")
        if url and url not in urls:
            urls.append(url)
    # 部分搜索卡片只返回封面；至少识别封面，完整多图仍以 image_list 为准。
    if not urls and isinstance(note_card.get("cover"), dict):
        cover = note_card["cover"]
        candidates = [cover.get("url_default"), cover.get("url_pre"), cover.get("url")]
        for info in cover.get("info_list", []) or []:
            if isinstance(info, dict):
                candidates.append(info.get("url"))
        url = next((value for value in candidates if isinstance(value, str) and value.startswith("http")), "")
        if url:
            urls.append(url)
    return urls


def find_xhs_detail_image_urls(payload: object, note_id: str) -> list[str]:
    """从详情页自身返回的数据中寻找目标笔记的完整图片组，不额外请求接口。"""
    best: list[str] = []
    stack = [payload]
    while stack:
        value = stack.pop()
        if isinstance(value, dict):
            candidate_id = str(value.get("note_id") or value.get("id") or "")
            if candidate_id == note_id and value.get("image_list"):
                urls = xhs_image_urls(value)
                if len(urls) > len(best):
                    best = urls
            stack.extend(value.values())
        elif isinstance(value, list):
            stack.extend(value)
    return best


def ocr_xhs_images(context, note_id: str, image_urls: list[str], max_images: int) -> str:
    if not image_urls or max_images <= 0:
        return ""
    try:
        from rapidocr import RapidOCR
        engine = RapidOCR(params={"Global.log_level": "critical"})
    except Exception as exc:
        print(f"OCR 引擎不可用，跳过图片识别：{exc}")
        return ""

    target_dir = IMAGE_DIR / note_id
    target_dir.mkdir(parents=True, exist_ok=True)
    pages: list[str] = []
    for index, image_url in enumerate(image_urls[:max_images], start=1):
        try:
            response = context.request.get(image_url, timeout=30_000)
            if not response.ok:
                print(f"图片 {index} 下载失败：HTTP {response.status}")
                continue
            image_path = target_dir / f"{index:02d}.jpg"
            image_path.write_bytes(response.body())
            result = engine(image_path)
            texts = list(getattr(result, "txts", None) or [])
            scores = list(getattr(result, "scores", None) or [])
            lines = [clean_text(text) for text, score in zip(texts, scores) if score >= 0.55 and clean_text(text)]
            if lines:
                pages.append(f"[图片OCR 第{index}页]\n" + "\n".join(lines))
        except Exception as exc:
            print(f"图片 {index} OCR 失败：{exc}")
    return "\n".join(pages)


def xhs_search_ready(page) -> bool:
    """只有真实搜索卡片出现时才认为登录和验证均已完成。"""
    try:
        return page.locator('a[href*="/explore/"]').count() > 0
    except Exception:
        return False


def wait_for_xhs_search(page, seconds: int) -> bool:
    """等待用户手动登录/验证；不读取凭据，也不把登录页误判为成功。"""
    deadline = time.time() + seconds
    while time.time() < deadline:
        page.wait_for_timeout(3000)
        if xhs_search_ready(page):
            return True
    return False


def collect_xhs(context, keywords: list[str], limit: int, delay: float, enable_ocr: bool = True,
                ocr_max_images: int = 9, exclude_note_ids: set[str] | None = None,
                checkpoint: Any | None = None) -> list[Post]:
    posts: list[Post] = []
    seen_note_ids: set[str] = set(exclude_note_ids or set())
    # CDP 连接的浏览器可能已有用户标签页。采集器只操作自己新建的标签，
    # 不关闭或复用用户正在浏览的页面。
    page = context.new_page()

    # 先进入站点首页，让真实 Chrome 完成 Cookie、安全脚本和前端运行时初始化。
    # 直接从 about:blank 跳到搜索页，容易得到已提交但尚未水合的空壳页面。
    try:
        page.goto("https://www.xiaohongshu.com/explore", wait_until="commit", timeout=30_000)
    except Exception as exc:
        print(f"小红书首页预热导航未正常结束，继续等待当前页面：{exc}")
    page.wait_for_timeout(15_000)
    try:
        warm_body = page.locator("body").inner_text(timeout=10_000)
    except Exception:
        warm_body = ""
    if not warm_body:
        print("小红书首页预热失败：页面正文为空。本轮不进入搜索。")
        if checkpoint:
            checkpoint.mark_failed("xhs:session", "首页预热正文为空")
        return posts
    warm_blocked = page_blocked(warm_body)
    if warm_blocked and "验证码" in warm_blocked:
        save_block_evidence(page, "xhs_warmup_blocked", warm_body)
        print(warm_blocked)
        if checkpoint:
            checkpoint.mark_failed("xhs:session", warm_blocked)
        return posts
    print("小红书首页预热完成，准备进入关键词搜索。")

    for keyword in keywords:
        keyword_key = f"xhs:keyword:{keyword}"
        if checkpoint and checkpoint.is_done(keyword_key):
            print(f"断点续跑：跳过已完成关键词 {keyword}")
            continue
        captured_items: dict[str, dict] = {}
        keyword_complete = True

        def capture_search_response(response) -> None:
            # 被动读取当前搜索页自己发出的响应，不额外请求接口。
            if "/api/sns/web/v2/search/notes" not in response.url or response.status != 200:
                return
            try:
                payload = response.json()
                for item in payload.get("data", {}).get("items", []):
                    note_id = item.get("id", "")
                    token = item.get("xsec_token", "")
                    if note_id and token:
                        captured_items.setdefault(note_id, item)
            except Exception as exc:
                print(f"解析搜索响应失败：{exc}")

        page.on("response", capture_search_response)
        search_url = f"https://www.xiaohongshu.com/search_result?keyword={quote(keyword)}&type=51"
        try:
            # 小红书有持续连接和前端风控脚本，等待 DOMContentLoaded 可能长期不返回。
            # commit 只要求主文档开始响应，随后再显式等待可见正文。
            page.goto(search_url, wait_until="commit", timeout=30_000)
        except Exception as exc:
            # 某些风控页会让 domcontentloaded 一直不结束；仍检查浏览器已渲染的内容。
            print(f"页面导航未正常结束，继续检查当前页面：{exc}")
        page.wait_for_timeout(3500)
        try:
            body = page.locator("body").inner_text(timeout=15_000)
        except Exception:
            body = ""
        if not body:
            # commit 超时时主文档可能仍在加载。这里只等待当前请求完成，不刷新、
            # 不重发搜索请求，最多观察 60 秒。
            deadline = time.time() + 60
            while time.time() < deadline and not body:
                page.wait_for_timeout(3000)
                try:
                    body = page.locator("body").inner_text(timeout=5000)
                except Exception:
                    body = ""
        if not body:
            save_block_evidence(page, "xhs_empty", f"URL: {page.url}\n页面没有可读取正文。")
            print("小红书页面没有返回可读取正文，已保存诊断截图。")
            if checkpoint:
                checkpoint.mark_failed(keyword_key, "搜索页正文为空")
            return posts
        blocked = page_blocked(body)
        if blocked and "登录" in blocked:
            save_block_evidence(page, "xhs_login", body)
            print(blocked)
            print("请在 180 秒内完成登录；程序不会读取或打印 Cookie。")
            if not wait_for_xhs_search(page, 300):
                print("等待登录超时，跳过小红书。")
                if checkpoint:
                    checkpoint.mark_failed(keyword_key, "等待登录超时")
                return posts
            print("已检测到搜索结果，静置 15 秒后开始低频采集。")
            page.wait_for_timeout(15_000)
        elif blocked:
            save_block_evidence(page, "xhs_blocked", body)
            print(blocked)
            print("浏览器将保留 300 秒，请由用户本人完成验证；程序不会自动操作验证码。")
            if not wait_for_xhs_search(page, 300):
                print("等待验证超时，跳过小红书。")
                if checkpoint:
                    checkpoint.mark_failed(keyword_key, "等待验证超时")
                return posts
            print("已检测到搜索结果，静置 15 秒后开始低频采集。")
            page.wait_for_timeout(15_000)

        links: dict[str, dict] = {}
        stale = 0
        while len(links) < limit and stale < 4:
            before = len(links)
            for note_id, item in captured_items.items():
                if note_id in seen_note_ids:
                    continue
                token = item.get("xsec_token", "")
                card = item.get("note_card", {}) or {}
                title = clean_text(card.get("display_title", ""))[:120]
                query = urlencode({"xsec_token": token, "xsec_source": "pc_search"})
                url = f"https://www.xiaohongshu.com/explore/{note_id}?{query}"
                links.setdefault(url, {
                    "title": title,
                    "images": xhs_image_urls(card),
                    "gallery_count": len(card.get("image_list", []) or []),
                })
            stale = stale + 1 if len(links) == before else 0
            if len(links) < limit:
                page.mouse.wheel(0, 1800)
                page.wait_for_timeout(int(delay * 1000))
        page.remove_listener("response", capture_search_response)
        print(f"搜索响应中取得 {len(links)} 条带 xsec_token 的笔记结果。")
        if not links:
            keyword_complete = bool(captured_items) and all(
                note_id in seen_note_ids for note_id in captured_items
            )

        for url, link_info in list(links.items())[:limit]:
            card_title = link_info["title"]
            image_urls = link_info["images"]
            gallery_count = link_info.get("gallery_count", 0)
            note_id = urlparse(url).path.rsplit("/", 1)[-1]
            item_key = f"xhs:note:{note_id}"
            if checkpoint and checkpoint.is_done(item_key):
                continue
            seen_note_ids.add(note_id)
            if "xsec_token=" not in url:
                print(f"跳过缺少 xsec_token 的详情链接：{url}")
                if card_title:
                    posts.append(Post("小红书", card_title, url, card_title,
                                      infer_company(card_title, ""), confidence="C", keyword=keyword))
                    persist_raw(posts[-1])
                if checkpoint:
                    checkpoint.mark_done(item_key)
                continue
            detail = context.new_page()
            detail_image_urls: list[str] = []

            def capture_detail_response(response) -> None:
                nonlocal detail_image_urls
                if "/api/sns/web/" not in response.url:
                    return
                try:
                    urls = find_xhs_detail_image_urls(response.json(), note_id)
                    if len(urls) > len(detail_image_urls):
                        detail_image_urls = urls
                except Exception:
                    return

            detail.on("response", capture_detail_response)
            try:
                detail.goto(url, wait_until="commit", timeout=30_000)
                detail.wait_for_timeout(8000)
                text = clean_text(detail.locator("body").inner_text(timeout=15_000))
                blocked = page_blocked(text)
                if blocked:
                    print(f"{url.split('?')[0]}: {blocked}")
                    if card_title:
                        posts.append(Post("小红书", card_title, url, card_title,
                                          infer_company(card_title, ""), confidence="C", keyword=keyword))
                        persist_raw(posts[-1])
                    if "验证码" in blocked:
                        if checkpoint:
                            checkpoint.mark_failed(keyword_key, blocked)
                        return posts
                    keyword_complete = False
                    continue
                title = detail.title() or card_title
                desc = detail.locator('meta[name="description"]').get_attribute("content") if detail.locator('meta[name="description"]').count() else ""
                content = extract_xhs_note_text(text, card_title, desc or "")
                used_ocr = False
                if len(detail_image_urls) > len(image_urls):
                    image_urls = detail_image_urls
                    gallery_count = len(detail_image_urls)
                if enable_ocr and image_urls and (gallery_count > 0 or len(split_questions(content)) < 3):
                    ocr_text = ocr_xhs_images(context, note_id, image_urls, ocr_max_images)
                    if ocr_text:
                        content = clean_text(content + "\n" + ocr_text)
                        used_ocr = True
                image_dir = IMAGE_DIR / note_id
                downloaded = len(list(image_dir.glob("*"))) if used_ocr and image_dir.exists() else 0
                ocr_pages = content.count("[图片OCR 第")
                expected = gallery_count or (len(image_urls) if image_urls else 0)
                posts.append(Post(
                    "小红书", title[:160], url, content, infer_company(title, content),
                    confidence="C" if used_ocr else "B", keyword=keyword,
                    collection_depth="deep" if used_ocr else "text",
                    expected_image_count=expected, downloaded_image_count=downloaded,
                    ocr_page_count=ocr_pages,
                    is_complete=(expected == 0 or (used_ocr and downloaded >= expected and ocr_pages >= expected)),
                ))
                persist_raw(posts[-1])
                if checkpoint:
                    checkpoint.mark_done(item_key)
            except Exception as exc:
                print(f"读取失败 {url}: {exc}")
                keyword_complete = False
                if checkpoint:
                    checkpoint.mark_failed(item_key, exc)
                if card_title:
                    posts.append(Post("小红书", card_title, url, card_title,
                                      infer_company(card_title, ""), confidence="C", keyword=keyword))
                    persist_raw(posts[-1])
            finally:
                detail.close()
            time.sleep(delay)
        if checkpoint and keyword_complete:
            checkpoint.mark_done(keyword_key)
        elif checkpoint:
            checkpoint.mark_failed(keyword_key, "关键词仍有未完成或失败的详情页")
    return posts

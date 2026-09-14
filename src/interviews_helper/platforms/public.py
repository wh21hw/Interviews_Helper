from __future__ import annotations
import re
import time
from typing import Any
from urllib.parse import urlparse
from ..models import Post
from ..pipeline.questions import clean_text, infer_company
from ..runtime import page_blocked
from ..storage.repository import persist_raw


def longest_visible_text(page, selectors: tuple[str, ...]) -> str:
    """从站点常用正文容器中选择最长的可见文本。"""
    candidates: list[str] = []
    for selector in selectors:
        try:
            locator = page.locator(selector)
            for index in range(min(locator.count(), 8)):
                item = locator.nth(index)
                if item.is_visible():
                    value = clean_text(item.inner_text(timeout=5_000))
                    if value:
                        candidates.append(value)
        except Exception:
            continue
    return max(candidates, key=len, default="")


def first_selector_text(page, selectors: tuple[str, ...]) -> str:
    """按优先级选择正文容器，同一选择器存在多个节点时取首个可读节点。"""
    for selector in selectors:
        try:
            locator = page.locator(selector)
            for index in range(min(locator.count(), 8)):
                item = locator.nth(index)
                if not item.is_visible():
                    continue
                value = clean_text(item.inner_text(timeout=5_000))
                if len(value) >= 80:
                    return value
        except Exception:
            continue
    return ""


def clean_public_title(title: str, host: str) -> str:
    """清除登录用户的通知数量等动态前缀，保持来源标题与标识稳定。"""
    value = clean_text(title)
    if "zhihu" in host.lower():
        value = re.sub(r"^\([^)]*(?:私信|消息)[^)]*\)\s*", "", value)
    return value[:160]


def extract_public_main_text(page, host: str, body: str) -> str:
    """按站点正文容器抽取文章，失败时再对 body 做边界裁剪。"""
    host = host.lower()
    if "nowcoder" in host:
        selected = longest_visible_text(page, (
            ".post-topic-main", ".post-content", ".nc-post-content", ".article-content",
            ".markdown-body", "article", "main",
        ))
        value = selected or body
        # 牛客公开正文之后通常紧接订阅提示、评论和相关推荐。
        for marker in ("\n提示\n订阅专刊", "\n全部评论", "\n相关推荐", "\n暂无评论"):
            if marker in value:
                value = value.split(marker, 1)[0]
        return clean_text(value)
    if "zhihu" in host:
        selected = first_selector_text(page, (
            ".AnswerItem .RichContent-inner", ".Post-RichTextContainer", ".RichContent-inner",
            "article .RichText", "article", "main",
        ))
        return clean_text(selected or body)
    if "weixin" in host:
        selected = longest_visible_text(page, ("#js_content", ".rich_media_content", "article", "main"))
        return clean_text(selected or body)
    return clean_text(longest_visible_text(page, ("article", "main")) or body)


def wait_for_public_content(page, host: str, seconds: int) -> str:
    """等待用户在真实浏览器中完成登录或验证，成功后返回正文。"""
    deadline = time.time() + seconds
    while time.time() < deadline:
        page.wait_for_timeout(3000)
        try:
            body = clean_text(page.locator("body").inner_text(timeout=5000))
            main_text = extract_public_main_text(page, host, body)
            if not page_blocked(body) and len(main_text) >= 80:
                return main_text
        except Exception:
            continue
    return ""


def collect_public_pages(context, urls: list[str], delay: float, manual_login_wait: int = 300,
                         checkpoint: Any | None = None) -> list[Post]:
    posts: list[Post] = []
    blocked_hosts: set[str] = set()
    for url in urls:
        item_key = f"web:url:{url.split('#', 1)[0]}"
        if checkpoint and checkpoint.is_done(item_key):
            print(f"断点续跑：跳过已完成 URL {url}")
            continue
        host = urlparse(url).netloc.lower()
        if host in blocked_hosts:
            if checkpoint:
                checkpoint.mark_failed(item_key, f"同域名 {host} 已触发登录或验证阻断")
            continue
        page = context.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_timeout(2000)
            body = clean_text(page.locator("body").inner_text(timeout=20_000))
            blocked = page_blocked(body)
            if blocked:
                print(f"{url}: {blocked}")
                print(f"请在 {manual_login_wait} 秒内于打开的浏览器中手动完成；程序不会读取凭据。")
                main_text = wait_for_public_content(page, host, manual_login_wait)
                if not main_text:
                    blocked_hosts.add(host)
                    if checkpoint:
                        checkpoint.mark_failed(item_key, blocked or "登录或验证等待超时")
                    continue
                print(f"{host}: 已检测到可读正文，继续低频采集。")
            title = clean_public_title(page.title(), host)
            platform = ("牛客" if "nowcoder" in host else "知乎" if "zhihu" in host
                        else "微信公众号" if "weixin" in host else host)
            main_text = main_text if blocked else extract_public_main_text(page, host, body)
            if len(main_text) < 80:
                print(f"正文过短，跳过 {url}")
                if checkpoint:
                    checkpoint.mark_failed(item_key, "正文不足 80 字")
                continue
            posts.append(Post(platform, title, url, main_text, infer_company(title, main_text)))
            persist_raw(posts[-1])
            if checkpoint:
                checkpoint.mark_done(item_key)
        except Exception as exc:
            print(f"读取失败 {url}: {exc}")
            if checkpoint:
                checkpoint.mark_failed(item_key, exc)
        finally:
            page.close()
        time.sleep(delay)
    return posts


def public_profile_key(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if "nowcoder" in host:
        return "nowcoder"
    if "zhihu" in host:
        return "zhihu"
    if "weixin" in host:
        return "weixin"
    return "web"

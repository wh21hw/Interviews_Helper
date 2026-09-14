from __future__ import annotations
import subprocess
import time
from pathlib import Path
from typing import Any
from .models import Post
from .platforms.public import collect_public_pages
from .platforms.xiaohongshu import collect_xhs
from .runtime import cdp_websocket_url, chrome_path, launch_chrome_cdp, require_playwright


def crawl(
    keywords: list[str], urls: list[str], limit: int, delay: float, profile: Path,
    proxy: str | None = None, backend: str = "cdp", cdp_port: int = 9222,
    enable_ocr: bool = True, ocr_max_images: int = 9, exclude_note_ids: set[str] | None = None,
    manual_login_wait: int = 300,
    checkpoint: Any | None = None,
) -> list[Post]:
    sync_playwright = require_playwright()
    profile.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = None
        chrome_process = None
        if backend == "cdp":
            chrome_process, actual_port = launch_chrome_cdp(profile, proxy, cdp_port)
            try:
                browser = p.chromium.connect_over_cdp(cdp_websocket_url(actual_port))
            except Exception:
                if chrome_process.poll() is None:
                    chrome_process.terminate()
                    try:
                        chrome_process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        chrome_process.kill()
                raise
            if not browser.contexts:
                raise RuntimeError("已连接 Chrome，但没有可用浏览器上下文。")
            context = browser.contexts[0]
            print(f"已通过 CDP 连接真实 Chrome：127.0.0.1:{actual_port}")
        else:
            launch_options = {
                "executable_path": str(chrome_path()), "headless": False,
                "viewport": {"width": 1440, "height": 960},
            }
            if proxy:
                launch_options["proxy"] = {"server": proxy}
            context = p.chromium.launch_persistent_context(str(profile), **launch_options)
        context.set_default_timeout(20_000)
        original_pages = set(context.pages)
        try:
            posts = collect_xhs(context, keywords, limit, delay, enable_ocr, ocr_max_images,
                                exclude_note_ids, checkpoint) if keywords else []
            posts.extend(collect_public_pages(context, urls, delay, manual_login_wait, checkpoint))
            return posts
        finally:
            for opened_page in list(context.pages):
                if opened_page not in original_pages:
                    try:
                        opened_page.close()
                    except Exception:
                        pass
            if backend == "persistent":
                context.close()
            elif browser is not None and chrome_process is not None:
                # 该 Chrome 由本次任务用专用 profile 启动，可以安全关闭；登录态会落盘。
                browser.close()
                try:
                    chrome_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    chrome_process.terminate()
                    try:
                        chrome_process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        chrome_process.kill()


def prepare_manual_login(platform: str, profile: Path, proxy: str | None, cdp_port: int,
                         wait_seconds: int) -> None:
    """打开平台首页供用户自行登录；关闭该标签页即保存状态并结束等待。"""
    urls = {
        "xhs": "https://www.xiaohongshu.com/explore",
        "nowcoder": "https://www.nowcoder.com/",
        "zhihu": "https://www.zhihu.com/",
        "weixin": "https://mp.weixin.qq.com/",
    }
    profile.mkdir(parents=True, exist_ok=True)
    sync_playwright = require_playwright()
    with sync_playwright() as playwright:
        process, port = launch_chrome_cdp(profile, proxy, cdp_port)
        browser = playwright.chromium.connect_over_cdp(cdp_websocket_url(port))
        if not browser.contexts:
            raise RuntimeError("已连接 Chrome，但没有可用浏览器上下文。")
        context = browser.contexts[0]
        page = context.new_page()
        try:
            page.goto(urls[platform], wait_until="commit", timeout=30_000)
        except Exception:
            pass
        print(f"已打开 {platform} 手动登录页：{profile.resolve()}")
        print(f"请自行完成登录，完成后关闭该登录标签页；最长等待 {wait_seconds} 秒。")
        deadline = time.time() + wait_seconds
        while time.time() < deadline and process.poll() is None and not page.is_closed():
            try:
                page.wait_for_timeout(1000)
            except Exception:
                break
        if not page.is_closed():
            try:
                page.close()
            except Exception:
                pass
        try:
            browser.close()
        except Exception:
            pass
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()

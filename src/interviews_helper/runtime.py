from __future__ import annotations
import json
import socket
import subprocess
import shutil
import time
from pathlib import Path
from urllib.request import ProxyHandler, build_opener
from .config import CHROME_PATHS, DATA_DIR


def chrome_path() -> Path:
    for path in CHROME_PATHS:
        if path.exists():
            return path
    for executable in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "msedge"):
        resolved = shutil.which(executable)
        if resolved:
            return Path(resolved)
    raise RuntimeError("没有找到 Chrome/Edge。请安装浏览器或在 config.py 的 CHROME_PATHS 中配置路径。")


def require_playwright():
    try:
        from playwright.sync_api import sync_playwright
        return sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "尚未安装 Playwright。请在项目目录运行：python -m pip install -e .。"
            "若网络暂时不可用，可以先运行 interviews-helper build 生成示例报告。"
        ) from exc


def page_blocked(text: str) -> str | None:
    lower = text.lower()
    if "验证码" in text or "安全验证" in text or "captcha" in lower:
        return "检测到验证码/安全验证，程序已停止当前平台，请手动处理后重新运行。"
    if any(message in text for message in ("你访问的页面不见了", "页面不见了", "笔记不存在", "当前笔记暂时无法浏览")):
        return "笔记详情不可用或缺少有效的搜索上下文参数。"
    if "登录后" in text or "扫码登录" in text or "登录以查看更多" in text:
        return "检测到登录页面。请在打开的浏览器中自行登录，登录态会保存在本地 profile。"
    return None


def save_block_evidence(page, name: str, body: str) -> None:
    """只在本地保存诊断材料，不读取 Cookie 或浏览器存储。"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / f"{name}.txt").write_text(body[:20_000], encoding="utf-8")
    try:
        page.screenshot(path=str(DATA_DIR / f"{name}.png"), full_page=False)
    except Exception as exc:
        print(f"拦截页截图保存失败：{exc}")


def tcp_port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def launch_chrome_cdp(profile: Path, proxy: str | None, preferred_port: int) -> tuple[subprocess.Popen, int]:
    """启动独立真实 Chrome；只开放本机 CDP 端口。"""
    port = next((p for p in range(preferred_port, preferred_port + 20) if not tcp_port_open(p)), None)
    if port is None:
        raise RuntimeError("9222 附近没有可用的 CDP 调试端口。")
    args = [
        str(chrome_path()),
        f"--remote-debugging-port={port}",
        "--remote-debugging-address=127.0.0.1",
        f"--user-data-dir={profile.resolve()}",
        "--no-first-run",
        "--disable-session-crashed-bubble",
        "--new-window",
        "about:blank",
    ]
    if proxy:
        args.insert(-2, f"--proxy-server={proxy}")
    process = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.time() + 25
    while time.time() < deadline:
        if tcp_port_open(port):
            return process, port
        if process.poll() is not None:
            break
        time.sleep(0.5)
    if process.poll() is None:
        process.terminate()
    raise RuntimeError("真实 Chrome 的 CDP 端口未启动；请关闭占用该专用 profile 的 Chrome 后重试。")


def cdp_websocket_url(port: int) -> str:
    """直连本机 DevTools，避免 HTTP_PROXY 把 localhost 转发到外部代理。"""
    opener = build_opener(ProxyHandler({}))
    with opener.open(f"http://127.0.0.1:{port}/json/version", timeout=5) as response:
        payload = json.loads(response.read().decode("utf-8"))
    endpoint = payload.get("webSocketDebuggerUrl")
    if not endpoint:
        raise RuntimeError("CDP 服务没有返回 WebSocket 地址。")
    return endpoint

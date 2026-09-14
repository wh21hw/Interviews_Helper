from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from .config import DATA_DIR, IMAGE_DIR
from .models import Post
from .pipeline.questions import infer_business, infer_company, infer_date
from .report.builder import build_rows, render_html
from .storage.repository import load_raw_posts, load_seed, post_identity, save_database, save_posts


def generate_keywords(job: str, explicit: str = "") -> list[str]:
    if explicit.strip():
        return list(dict.fromkeys(item.strip() for item in explicit.split(",") if item.strip()))
    job = job.strip()
    return [f"{job} 面经", f"{job} 一面", f"{job} 面试题"] if job else []


def load_library(seed: Path | None = None, include_raw: bool = True) -> list[Post]:
    posts: list[Post] = []
    if seed and seed.exists():
        posts.extend(load_seed(seed))
    existing = DATA_DIR / "interviews.json"
    if existing.exists():
        posts.extend(load_seed(existing))
    if include_raw:
        posts.extend(load_raw_posts())
    return posts


def normalize_library(posts: list[Post]) -> list[Post]:
    unique: dict[str, Post] = {}
    for post in posts:
        company = infer_company(post.title, post.text)
        if company != "其他/未知":
            post.company = company
        business = infer_business(post.title, post.text)
        if business != "待识别" and post.business in ("待识别", ""):
            post.business = business
        if not post.date:
            post.date = infer_date(post.text)
        if post.platform == "小红书":
            note_id = urlparse(post.url).path.rsplit("/", 1)[-1]
            image_dir = IMAGE_DIR / note_id
            downloaded = len(list(image_dir.glob("*"))) if image_dir.exists() else 0
            pages = post.text.count("[图片OCR 第")
            if pages:
                post.collection_depth = "deep"
                post.ocr_page_count = pages
                post.downloaded_image_count = max(post.downloaded_image_count, downloaded)
                if not post.expected_image_count:
                    post.is_complete = False
        identity = post_identity(post)
        previous = unique.get(identity)
        score = (len(post.text), post.ocr_page_count, post.downloaded_image_count, post.collected_at)
        previous_score = (
            len(previous.text), previous.ocr_page_count, previous.downloaded_image_count,
            previous.collected_at,
        ) if previous else None
        if previous is None or score > previous_score:
            unique[identity] = post
    return list(unique.values())


def build_library(posts: list[Post], database: Path, output: Path) -> tuple[list[Post], list[dict]]:
    posts = normalize_library(posts)
    questions = build_rows(posts)
    save_posts(posts, DATA_DIR / "interviews.json")
    save_database(posts, questions, database)
    render_html(posts, questions, output)
    return posts, questions

from __future__ import annotations
import hashlib
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from ..models import Post
from ..pipeline.questions import deduplicate_questions, extract_question_candidates, infer_business, infer_company, topic_of
from ..storage.repository import post_identity


def build_rows(posts: list[Post]) -> list[dict]:
    rows: list[dict] = []
    for idx, post in enumerate(posts):
        source_id = hashlib.sha1(post_identity(post).encode("utf-8")).hexdigest()[:16]
        for candidate in extract_question_candidates(post.text):
            question = candidate["question"]
            question_business = infer_business(question, "")
            if question_business == "待识别":
                question_business = post.business
            rows.append({
                "question": question,
                "topic": topic_of(question),
                "company": post.company if post.company != "待识别" else infer_company(post.title, post.text),
                "business": question_business,
                "platform": post.platform,
                "confidence": post.confidence,
                "source": {
                    "post_id": idx, "source_id": source_id, "title": post.title, "url": post.url,
                    "date": post.date, "company": post.company, "platform": post.platform,
                    "confidence": post.confidence, "evidence": candidate["evidence"],
                    "is_complete": post.is_complete, "collection_depth": post.collection_depth,
                },
            })
    return deduplicate_questions(rows)


def render_html(posts: list[Post], questions: list[dict], output: Path) -> None:
    payload = json.dumps({"posts": [asdict(p) for p in posts], "questions": questions}, ensure_ascii=False).replace("</", "<\\/")
    template = Path(__file__).with_name("template.html").read_text(encoding="utf-8")
    result = template.replace("__DATA__", payload).replace("__GENERATED_AT__", datetime.now().strftime("%Y-%m-%d %H:%M"))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(result, encoding="utf-8")

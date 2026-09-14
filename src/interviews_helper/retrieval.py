from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
from collections import Counter
from pathlib import Path


def _terms(text: str) -> list[str]:
    text = text.lower().strip()
    latin = re.findall(r"[a-z0-9+#.]{2,}", text)
    chinese = re.sub(r"[^\u4e00-\u9fff]", "", text)
    grams = [chinese[i:i + size] for size in (2, 3) for i in range(max(0, len(chinese) - size + 1))]
    return latin + grams


def _vector(text: str, dimensions: int = 1024) -> Counter[int]:
    result: Counter[int] = Counter()
    for term in _terms(text):
        digest = hashlib.blake2b(term.encode("utf-8"), digest_size=8).digest()
        result[int.from_bytes(digest, "little") % dimensions] += 1
    return result


def _cosine(left: Counter[int], right: Counter[int]) -> float:
    if not left or not right:
        return 0.0
    numerator = sum(value * right.get(index, 0) for index, value in left.items())
    denominator = math.sqrt(sum(value * value for value in left.values())) * math.sqrt(
        sum(value * value for value in right.values())
    )
    return numerator / denominator if denominator else 0.0


def _load_documents(database: Path) -> list[dict]:
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            """SELECT question_id, question, topic, frequency, confidence, quality_score,
                      companies_json, platforms_json, businesses_json
               FROM questions"""
        ).fetchall()
        documents = []
        for row in rows:
            item = dict(row)
            for field in ("companies_json", "platforms_json", "businesses_json"):
                item[field.removesuffix("_json")] = json.loads(item.pop(field))
            sources = connection.execute(
                """SELECT p.title, p.url, p.platform, qs.evidence_excerpt
                   FROM question_sources qs JOIN posts p ON p.source_id=qs.source_id
                   WHERE qs.question_id=?""",
                (item["question_id"],),
            ).fetchall()
            item["sources"] = [dict(source) for source in sources]
            documents.append(item)
        return documents
    finally:
        connection.close()


def hybrid_search(
    query: str,
    database: Path,
    *,
    top_k: int = 20,
    grep_pattern: str | None = None,
    encoder: str = "hashing",
    model_name: str = "BAAI/bge-small-zh-v1.5",
) -> list[dict]:
    """Combine exact/regex recall and vector recall with reciprocal-rank fusion."""
    documents = _load_documents(database)
    query_terms = set(_terms(query))
    query_vector = _vector(query)
    pattern = re.compile(grep_pattern, re.IGNORECASE) if grep_pattern else None
    lexical: list[tuple[float, int]] = []
    semantic: list[tuple[float, int]] = []
    haystacks: list[str] = []
    for index, item in enumerate(documents):
        haystack = " ".join([
            item["question"], item.get("topic") or "", *item["companies"], *item["businesses"]
        ])
        document_terms = set(_terms(haystack))
        overlap = len(query_terms & document_terms) / max(1, len(query_terms))
        exact = 1.0 if query.lower() in haystack.lower() else 0.0
        regex = 1.0 if pattern and pattern.search(haystack) else 0.0
        lexical.append((overlap + exact + regex, index))
        haystacks.append(haystack)
        if encoder == "hashing":
            semantic.append((_cosine(query_vector, _vector(haystack)), index))
    if encoder == "sentence-transformers":
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "sentence-transformers 未安装；请安装 interviews-helper[vectors]，或使用 --encoder hashing"
            ) from exc
        model = SentenceTransformer(model_name)
        vectors = model.encode([query, *haystacks], normalize_embeddings=True, show_progress_bar=False)
        semantic = [(float(vectors[0] @ vector), index) for index, vector in enumerate(vectors[1:])]
    elif encoder != "hashing":
        raise ValueError(f"未知向量编码器：{encoder}")
    lexical.sort(reverse=True)
    semantic.sort(reverse=True)
    ranks: dict[int, float] = {}
    details: dict[int, dict[str, float]] = {}
    for name, ranking in (("grep", lexical), ("vector", semantic)):
        for rank, (score, index) in enumerate(ranking, start=1):
            if score <= 0:
                continue
            ranks[index] = ranks.get(index, 0.0) + 1.0 / (60 + rank)
            details.setdefault(index, {})[name] = round(score, 6)
    ordered = sorted(ranks, key=lambda index: (ranks[index], documents[index]["quality_score"]), reverse=True)
    results = []
    for index in ordered[:max(1, top_k)]:
        result = dict(documents[index])
        result["score"] = round(ranks[index], 8)
        result["recall"] = details[index]
        results.append(result)
    return results

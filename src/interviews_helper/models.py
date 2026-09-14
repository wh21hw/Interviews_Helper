from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Post:
    platform: str
    title: str
    url: str
    text: str
    company: str = "待识别"
    business: str = "待识别"
    date: str = ""
    confidence: str = "B"
    keyword: str = ""
    collected_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    source_type: str = "direct"
    collection_depth: str = "text"
    expected_image_count: int = 0
    downloaded_image_count: int = 0
    ocr_page_count: int = 0
    is_complete: bool = True

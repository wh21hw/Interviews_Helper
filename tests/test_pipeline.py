import inspect
import sqlite3
import tempfile
import unittest
from pathlib import Path

from interviews_helper.browser import crawl
from interviews_helper.models import Post
from interviews_helper.pipeline.questions import (
    deduplicate_questions, infer_company, infer_date, split_questions, topic_of,
)
from interviews_helper.platforms.public import clean_public_title, public_profile_key
from interviews_helper.platforms.xiaohongshu import (
    extract_xhs_note_text, find_xhs_detail_image_urls, xhs_image_urls,
)
from interviews_helper.report.builder import build_rows, render_html
from interviews_helper.storage.repository import load_seed, post_identity, save_database

ROOT = Path(__file__).resolve().parents[1]


class CrawlerTests(unittest.TestCase):
    def test_extract_and_classify(self):
        questions = split_questions("1. 自我介绍\n2. AUC是什么？\n3. 怎样解决新商品冷启动\n点赞 收藏")
        self.assertEqual(questions, ["AUC是什么？", "怎样解决新商品冷启动"])
        self.assertEqual(topic_of(questions[1]), "冷启动与迁移")

    def test_deduplicate_keeps_sources(self):
        base = {"topic": "指标与实验", "company": "字节跳动", "business": "推荐", "platform": "牛客", "confidence": "A"}
        rows = [
            {**base, "question": "AUC是什么？", "source": {"source_id": "a", "title": "a", "url": "a", "date": ""}},
            {**base, "question": "AUC 的含义是什么", "source": {"source_id": "b", "title": "b", "url": "b", "date": ""}},
        ]
        result = deduplicate_questions(rows, threshold=0.7)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["frequency"], 2)

    def test_deduplicate_aggregates_companies_and_counts_unique_sources(self):
        rows = [
            {"question": "AUC怎么计算？", "topic": "指标与实验", "company": "字节跳动", "business": "推荐", "platform": "牛客", "confidence": "A", "source": {"source_id": "a", "title": "a", "url": "a", "date": ""}},
            {"question": "AUC怎么计算？", "topic": "指标与实验", "company": "字节跳动", "business": "推荐", "platform": "牛客", "confidence": "A", "source": {"source_id": "a", "title": "a", "url": "a", "date": ""}},
            {"question": "AUC怎么计算？", "topic": "指标与实验", "company": "美团", "business": "搜索", "platform": "小红书", "confidence": "C", "source": {"source_id": "b", "title": "b", "url": "b", "date": ""}},
        ]
        result = deduplicate_questions(rows)
        self.assertEqual(result[0]["frequency"], 2)
        self.assertEqual(result[0]["companies"], ["字节跳动", "美团"])
        self.assertEqual(result[0]["platforms"], ["小红书", "牛客"])

    def test_xhs_main_text_excludes_recommendations_and_comments(self):
        body = "\n".join([
            "首页", "目标面经", "无关推荐", "作者", "关注", "目标面经",
            "1️⃣为什么使用多路召回", "2️⃣怎样处理数据稀疏", "#面经",
            "猜你想搜", "其他热门内容", "共 5 条评论", "评论区问题怎么答",
        ])
        result = extract_xhs_note_text(body, "目标面经", "备用摘要")
        self.assertIn("为什么使用多路召回", result)
        self.assertNotIn("无关推荐", result)
        self.assertNotIn("评论区问题", result)

    def test_xhs_image_urls_selects_one_url_per_image(self):
        card = {"image_list": [
            {"url_default": "https://img.example/1.jpg", "url_pre": "https://img.example/1-small.jpg"},
            {"info_list": [{"url": "https://img.example/2.jpg"}]},
        ]}
        self.assertEqual(xhs_image_urls(card), [
            "https://img.example/1.jpg", "https://img.example/2.jpg",
        ])
        self.assertEqual(xhs_image_urls({"cover": {"url_default": "https://img.example/cover.jpg"}}), [
            "https://img.example/cover.jpg",
        ])

    def test_detail_payload_selects_matching_note_gallery(self):
        payload = {"data": {"items": [
            {"id": "other", "image_list": [{"url": "https://img/other"}]},
            {"note_id": "target", "image_list": [{"url": "https://img/1"}, {"url": "https://img/2"}]},
        ]}}
        self.assertEqual(find_xhs_detail_image_urls(payload, "target"), [
            "https://img/1", "https://img/2",
        ])

    def test_infer_date_requires_explicit_year(self):
        self.assertEqual(infer_date("面试时间：2025/8/16"), "2025-08-16")
        self.assertEqual(infer_date("09-03 北京"), "")

    def test_public_platforms_use_separate_profiles(self):
        self.assertEqual(public_profile_key("https://www.nowcoder.com/discuss/example"), "nowcoder")
        self.assertEqual(public_profile_key("https://www.zhihu.com/question/example"), "zhihu")
        self.assertEqual(public_profile_key("https://mp.weixin.qq.com/s/abc"), "weixin")

    def test_public_title_removes_zhihu_notification_prefix(self):
        self.assertEqual(
            clean_public_title("(33 封私信 / 80 条消息) 后端工程师需要哪些技术？ - 知乎", "www.zhihu.com"),
            "后端工程师需要哪些技术？ - 知乎",
        )

    def test_post_identity_ignores_tracking_query_and_title(self):
        first = Post("牛客", "旧标题", "https://www.nowcoder.com/discuss/example?sourceSSR=post", "正文")
        second = Post("牛客", "新标题", "https://www.nowcoder.com/discuss/example?from=feed", "正文")
        self.assertEqual(post_identity(first), post_identity(second))

    def test_crawl_entrypoint_keeps_collection_pipeline(self):
        source = inspect.getsource(crawl)
        self.assertIn("collect_xhs", source)
        self.assertIn("collect_public_pages", source)
        self.assertIn("context.set_default_timeout", source)

    def test_numbered_ocr_fragments_are_kept(self):
        text = "1.自我介绍\n2.问基本情况\n3.多模态 embedding 生成方案\n4.手撕 最长递增子序列"
        self.assertEqual(split_questions(text), [
            "多模态 embedding 生成方案", "手撕 最长递增子序列",
        ])

    def test_company_prefers_title_over_other_companies_in_body(self):
        self.assertEqual(
            infer_company("腾讯 CDG 推荐广告算法面经 - 小红书", "此前面过字节推荐算法"),
            "腾讯",
        )
        self.assertEqual(
            infer_company("26秋招面经分享-京东零售推荐算法", "小红书上整理的面经"),
            "京东",
        )

    def test_html_is_standalone(self):
        posts = load_seed(ROOT / "examples" / "seed_data.example.json")
        rows = build_rows(posts)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report.html"
            render_html(posts, rows, output)
            text = output.read_text(encoding="utf-8")
            self.assertIn("Interviews Helper", text)
            self.assertIn("const DATA=", text)
            self.assertNotIn("__DATA__", text)

    def test_sqlite_contains_question_source_links(self):
        posts = [
            Post("示例", "缓存面经", "https://example.com/cache", "1. Redis 缓存穿透怎么解决？"),
            Post("示例", "网络面经", "https://example.com/network", "1. TCP 为什么需要三次握手？"),
        ]
        rows = build_rows(posts)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report.sqlite3"
            save_database(posts, rows, output)
            connection = sqlite3.connect(output)
            try:
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM posts").fetchone()[0], 2)
                self.assertGreater(connection.execute("SELECT COUNT(*) FROM question_sources").fetchone()[0], 0)
            finally:
                connection.close()


if __name__ == "__main__":
    unittest.main()

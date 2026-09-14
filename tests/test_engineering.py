import tempfile
import unittest
from pathlib import Path

from interviews_helper.models import Post
from interviews_helper.report.builder import build_rows
from interviews_helper.retrieval import hybrid_search
from interviews_helper.service import generate_keywords
from interviews_helper.storage.checkpoint import RunCheckpoint
from interviews_helper.storage.repository import save_database


class EngineeringTests(unittest.TestCase):
    def test_checkpoint_resumes_matching_incomplete_run(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = RunCheckpoint.open({"job": "后端"}, directory=root)
            first.mark_done("web:url:1")
            resumed = RunCheckpoint.open({"job": "后端"}, directory=root)
            self.assertEqual(first.run_id, resumed.run_id)
            self.assertTrue(resumed.is_done("web:url:1"))
            resumed.finish()
            third = RunCheckpoint.open({"job": "后端"}, directory=root)
            self.assertNotEqual(first.run_id, third.run_id)

    def test_failed_checkpoint_stays_resumable_until_failure_is_cleared(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = RunCheckpoint.open({"job": "前端"}, directory=root)
            first.mark_failed("web:url:1", "timeout")
            first.finish()
            self.assertEqual(first.state["status"], "partial")
            resumed = RunCheckpoint.open({"job": "前端"}, directory=root)
            self.assertEqual(first.run_id, resumed.run_id)
            resumed.mark_done("web:url:1")
            resumed.finish()
            self.assertEqual(resumed.state["status"], "complete")

    def test_hybrid_search_returns_relevant_question_with_sources(self):
        posts = [Post("示例", "Redis 面经", "https://example.com/1",
                      "1. Redis 缓存穿透怎么解决？\n2. TCP 为什么需要三次握手？")]
        questions = build_rows(posts)
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "library.sqlite3"
            save_database(posts, questions, database)
            results = hybrid_search("缓存穿透", database, top_k=1)
            self.assertIn("缓存穿透", results[0]["question"])
            self.assertEqual(results[0]["sources"][0]["url"], "https://example.com/1")

    def test_job_generates_agent_search_terms(self):
        self.assertEqual(generate_keywords("后端开发"), [
            "后端开发 面经", "后端开发 一面", "后端开发 面试题",
        ])
        self.assertEqual(generate_keywords("ignored", "Java 面经, 分布式面试"), [
            "Java 面经", "分布式面试",
        ])


if __name__ == "__main__":
    unittest.main()

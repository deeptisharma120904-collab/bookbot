"""
Unit tests to enforce the sacred anti-spoiler rule:
EVERY retrieval path must filter to page <= current_page BEFORE ranking
and before anything reaches the LLM.

Covers both 'dense' (cosine) and 'hybrid' (BM25+RRF) modes.
"""

import sys
import unittest
from pathlib import Path

_BOOKBOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BOOKBOT_DIR))

from backend.vector_store import init_db
from backend.retrieval import retrieve_context, retrieve_page_range, retrieve_all_read_chunks


class TestSpoilerFilter(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def test_retrieve_context_never_leaks_future_pages(self):
        """
        Verify retrieve_context strictly returns chunks with page_number <= current_page
        across multiple page boundaries and queries.
        """
        queries = [
            "Who is Aman?",
            "What happened in Bombay Bound?",
            "Tell me about the ending and the party",
            "Did anyone get married?",
            "What did Gagan say?",
            "Why was she angry?",
        ]
        pages_to_test = [5, 10, 25, 50, 92, 100, 150]

        for current_page in pages_to_test:
            for query in queries:
                with self.subTest(current_page=current_page, query=query):
                    res = retrieve_context(
                        query=query,
                        book_id="too_good_to_be_true",
                        current_page=current_page,
                        top_k=10,
                    )
                    retrieved_pages = res.get("page_numbers", [])
                    for p in retrieved_pages:
                        self.assertLessEqual(
                            p,
                            current_page,
                            f"SPOILER LEAK: Retrieved page {p} > current_page {current_page} for query '{query}'"
                        )

    def test_retrieve_all_read_chunks_never_leaks_future_pages(self):
        """
        Verify retrieve_all_read_chunks returns only pages <= current_page.
        """
        for current_page in [10, 50, 100]:
            with self.subTest(current_page=current_page):
                res = retrieve_all_read_chunks("too_good_to_be_true", current_page)
                retrieved_pages = res.get("page_numbers", [])
                for p in retrieved_pages:
                    self.assertLessEqual(
                        p,
                        current_page,
                        f"SPOILER LEAK: Retrieved page {p} > current_page {current_page}"
                    )

    def test_retrieve_page_range_strictly_within_bounds(self):
        """
        Verify retrieve_page_range strictly returns chunks within [start_page, end_page].
        """
        ranges = [(1, 5), (10, 20), (50, 75)]
        for start, end in ranges:
            with self.subTest(start=start, end=end):
                res = retrieve_page_range("too_good_to_be_true", start, end)
                retrieved_pages = res.get("page_numbers", [])
                for p in retrieved_pages:
                    self.assertTrue(
                        start <= p <= end,
                        f"Retrieved page {p} outside [{start}, {end}]"
                    )

    def test_hybrid_mode_never_leaks_future_pages(self):
        """
        Verify hybrid BM25+RRF retrieval ALSO enforces page_number <= current_page.
        This is the Phase 3 anti-spoiler regression test for hybrid mode.
        """
        queries = [
            "Who is Aman?",
            "Tell me about the ending",
            "What happened at the party?",
        ]
        pages_to_test = [5, 50, 100, 150]

        for current_page in pages_to_test:
            for query in queries:
                with self.subTest(current_page=current_page, query=query, mode="hybrid"):
                    res = retrieve_context(
                        query=query,
                        book_id="too_good_to_be_true",
                        current_page=current_page,
                        top_k=10,
                        mode="hybrid",
                    )
                    retrieved_pages = res.get("page_numbers", [])
                    for p in retrieved_pages:
                        self.assertLessEqual(
                            p,
                            current_page,
                            f"HYBRID SPOILER LEAK: Retrieved page {p} > current_page {current_page} for query '{query}'"
                        )


if __name__ == "__main__":
    unittest.main()

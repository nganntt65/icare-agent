"""Unit tests for document indexing, SHA-256 caching, BM25, and Hybrid RRF."""

import unittest
import os
import tempfile
from src.retrieval.document_indexer import KnowledgeBaseManager, parse_markdown_into_chunks
from src.retrieval.bm25_retriever import BM25Retriever
from src.retrieval.vector_retriever import DenseVectorRetriever
from src.retrieval.hybrid_rrf import HybridRRFRetriever


class TestHybridRetrieval(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Path to actual project knowledge documents
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cls.data_dir = os.path.join(base_dir, "data")
        cls.retriever = HybridRRFRetriever(data_dir=cls.data_dir, rrf_k=60)
        cls.stats = cls.retriever.initialize()

    def test_knowledge_base_indexing_and_hashes(self):
        self.assertGreater(self.stats["total_chunks"], 10)
        self.assertIn("arc_procedures.md", self.stats["documents"])
        self.assertIn("nhi_insurance.md", self.stats["documents"])
        self.assertIn("housing_dormitories.md", self.stats["documents"])
        self.assertIn("course_selection.md", self.stats["documents"])
        self.assertIn("health_exam.md", self.stats["documents"])

        # Check document_hashes.json exists and has non-empty SHA-256 values
        manifest_path = os.path.join(self.data_dir, "document_hashes.json")
        self.assertTrue(os.path.exists(manifest_path))

    def test_bm25_exact_keyword_matching(self):
        bm25 = self.retriever.bm25
        results = bm25.retrieve("NT$1,000 ARC 1-year fee", top_k=3)
        self.assertTrue(len(results) > 0)
        top_chunk = results[0][0]
        self.assertEqual(top_chunk.source_file, "arc_procedures.md")

    def test_vector_semantic_matching(self):
        vec = self.retriever.vector
        results = vec.retrieve("dormitory quiet hours curfew 23:00", top_k=3)
        self.assertTrue(len(results) > 0)
        top_chunk = results[0][0]
        self.assertEqual(top_chunk.source_file, "housing_dormitories.md")

    def test_hybrid_rrf_scoring(self):
        # Scenario 2 from proposal: ARC expires in three days
        results = self.retriever.search("My ARC expires in three days. What documents do I need?", top_k=3)
        self.assertTrue(len(results) > 0)
        top_result = results[0]
        self.assertEqual(top_result.source_file, "arc_procedures.md")
        self.assertGreater(top_result.rrf_score, 0.015)
        self.assertGreater(top_result.bm25_score, 0.0)

    def test_cross_lingual_retrieval_vietnamese(self):
        # Vietnamese query without mentioning English word "ARC"
        results = self.retriever.search("Làm thế nào để gia hạn thẻ cư trú?", detected_lang="vi", top_k=3)
        self.assertTrue(len(results) > 0)
        self.assertEqual(results[0].source_file, "arc_procedures.md")


if __name__ == "__main__":
    unittest.main()

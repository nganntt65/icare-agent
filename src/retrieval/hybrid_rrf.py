"""Hybrid Retrieval Engine with Reciprocal Rank Fusion (RRF).

Fuses BM25 sparse keyword rankings and dense vector semantic rankings
using the reciprocal rank formula: score = sum(1 / (k + rank)) with k=60.
"""

from typing import List, Dict, Any, Tuple
from pydantic import BaseModel
from src.retrieval.document_indexer import DocumentChunk, KnowledgeBaseManager
from src.retrieval.bm25_retriever import BM25Retriever
from src.retrieval.vector_retriever import DenseVectorRetriever
from src.nlp.cross_lingual_normalizer import normalize_query


class RankedResult(BaseModel):
    """Unified hybrid retrieval search result."""
    chunk_id: str
    source_file: str
    doc_title: str
    section_title: str
    content: str
    rrf_score: float
    bm25_rank: int
    bm25_score: float
    vector_rank: int
    vector_score: float


class HybridRRFRetriever:
    """Orchestrates hybrid retrieval combining BM25 and dense semantic search via RRF."""

    def __init__(self, data_dir: str, rrf_k: int = 60):
        self.data_dir = data_dir
        self.rrf_k = rrf_k
        self.kb_manager = KnowledgeBaseManager(data_dir)
        self.bm25 = BM25Retriever(k1=1.5, b=0.75)
        self.vector = DenseVectorRetriever()
        self.chunks: List[DocumentChunk] = []

    def initialize(self) -> Dict[str, Any]:
        """Loads and indexes knowledge documents.
        
        Returns:
            Dictionary with indexing stats.
        """
        self.chunks, reindexed = self.kb_manager.load_or_index()
        self.bm25.index(self.chunks)
        self.vector.index(self.chunks)

        return {
            "total_chunks": len(self.chunks),
            "reindexed": reindexed,
            "documents": list(self.kb_manager.document_hashes.keys())
        }

    def search(
        self,
        query: str,
        detected_lang: str = "en",
        top_k: int = 4,
        candidate_depth: int = 10
    ) -> List[RankedResult]:
        """Performs hybrid search with cross-lingual normalization and RRF fusion.
        
        Args:
            query: User's search query.
            detected_lang: Language code ('en', 'zh', 'vi', 'id', 'tl', 'th').
            top_k: Number of fused results to return.
            candidate_depth: Number of candidates to fetch from each retriever.
            
        Returns:
            List of RankedResult items sorted by RRF score descending.
        """
        # 1. Apply cross-lingual term normalization
        enriched_query, detected_concepts = normalize_query(query, detected_lang)

        # 2. Retrieve candidates from both systems
        bm25_results = self.bm25.retrieve(enriched_query, top_k=candidate_depth)
        vector_results = self.vector.retrieve(enriched_query, top_k=candidate_depth)

        # 3. Compute Reciprocal Rank Fusion
        # Mapping: chunk_id -> dict of ranks and scores
        fused_scores: Dict[str, float] = {}
        chunk_map: Dict[str, DocumentChunk] = {}
        bm25_meta: Dict[str, Tuple[int, float]] = {}
        vector_meta: Dict[str, Tuple[int, float]] = {}

        for chunk, score, rank in bm25_results:
            cid = chunk.chunk_id
            chunk_map[cid] = chunk
            bm25_meta[cid] = (rank, score)
            fused_scores[cid] = fused_scores.get(cid, 0.0) + (1.0 / (self.rrf_k + rank))

        for chunk, score, rank in vector_results:
            cid = chunk.chunk_id
            chunk_map[cid] = chunk
            vector_meta[cid] = (rank, score)
            fused_scores[cid] = fused_scores.get(cid, 0.0) + (1.0 / (self.rrf_k + rank))

        # 4. Sort by RRF score descending
        sorted_cids = sorted(fused_scores.keys(), key=lambda x: fused_scores[x], reverse=True)

        final_results: List[RankedResult] = []
        for cid in sorted_cids[:top_k]:
            chunk = chunk_map[cid]
            b_rank, b_score = bm25_meta.get(cid, (candidate_depth + 1, 0.0))
            v_rank, v_score = vector_meta.get(cid, (candidate_depth + 1, 0.0))

            final_results.append(RankedResult(
                chunk_id=chunk.chunk_id,
                source_file=chunk.source_file,
                doc_title=chunk.doc_title,
                section_title=chunk.section_title,
                content=chunk.content,
                rrf_score=round(fused_scores[cid], 5),
                bm25_rank=b_rank,
                bm25_score=round(b_score, 4),
                vector_rank=v_rank,
                vector_score=round(v_score, 4)
            ))

        return final_results

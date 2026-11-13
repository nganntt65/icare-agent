"""High-Performance Pure-Python BM25Okapi Sparse Keyword Retriever.

Implements the Robertson BM25 algorithm with term-frequency saturation (k1=1.5)
and document-length penalization (b=0.75). Handles mixed multilingual tokens
(alphanumeric terms, acronyms, and CJK bi-grams).
"""

from typing import List, Dict, Tuple, Any
import math
import re
from src.retrieval.document_indexer import DocumentChunk


def tokenize(text: str) -> List[str]:
    """Tokenizes text into words and CJK character bi-grams for sparse matching."""
    text_clean = text.lower()
    # 1. Alphanumeric words (English, numbers, acronyms, diacritic words)
    words = re.findall(r"\b[\w-]+\b", text_clean)
    
    # 2. CJK character unigrams & bi-grams for Chinese queries
    cjk_chars = re.findall(r"[\u4e00-\u9fff]", text_clean)
    cjk_bigrams = [cjk_chars[i] + cjk_chars[i+1] for i in range(len(cjk_chars)-1)]
    
    tokens = words + cjk_chars + cjk_bigrams
    return [t for t in tokens if len(t.strip()) > 0]


class BM25Retriever:
    """BM25Okapi Inverted Index Retriever."""

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.chunks: List[DocumentChunk] = []
        self.doc_lengths: List[int] = []
        self.avg_doc_len: float = 0.0
        self.doc_count: int = 0
        self.term_doc_freq: Dict[str, int] = {}
        self.doc_term_freqs: List[Dict[str, int]] = []
        self.idf: Dict[str, float] = {}

    def index(self, chunks: List[DocumentChunk]) -> None:
        """Builds the BM25 inverted index over the provided document chunks."""
        self.chunks = chunks
        self.doc_count = len(chunks)
        self.doc_lengths = []
        self.doc_term_freqs = []
        self.term_doc_freq = {}

        if self.doc_count == 0:
            self.avg_doc_len = 0.0
            return

        total_length = 0

        for chunk in chunks:
            full_text = f"{chunk.doc_title} {chunk.section_title} {chunk.content}"
            tokens = tokenize(full_text)
            length = len(tokens)
            self.doc_lengths.append(length)
            total_length += length

            # Calculate term frequencies for this doc
            tf: Dict[str, int] = {}
            for token in tokens:
                tf[token] = tf.get(token, 0) + 1
            self.doc_term_freqs.append(tf)

            # Update document frequency for each unique term
            for token in tf.keys():
                self.term_doc_freq[token] = self.term_doc_freq.get(token, 0) + 1

        self.avg_doc_len = total_length / self.doc_count

        # Compute IDF for all vocabulary terms
        self.idf = {}
        for term, df in self.term_doc_freq.items():
            # Standard BM25 IDF with smoothing
            idf_score = math.log((self.doc_count - df + 0.5) / (df + 0.5) + 1.0)
            self.idf[term] = max(idf_score, 0.05)

    def retrieve(self, query: str, top_k: int = 5) -> List[Tuple[DocumentChunk, float, int]]:
        """Retrieves top_k chunks matching query using BM25 scoring.
        
        Returns:
            List of tuples: (DocumentChunk, bm25_score, rank_1_indexed)
        """
        if self.doc_count == 0:
            return []

        query_tokens = tokenize(query)
        scores = [0.0] * self.doc_count

        for q_token in query_tokens:
            if q_token not in self.idf:
                continue

            q_idf = self.idf[q_token]

            for doc_idx in range(self.doc_count):
                tf = self.doc_term_freqs[doc_idx].get(q_token, 0)
                if tf == 0:
                    continue

                doc_len = self.doc_lengths[doc_idx]
                numerator = tf * (self.k1 + 1.0)
                denominator = tf + self.k1 * (1.0 - self.b + self.b * (doc_len / self.avg_doc_len))
                scores[doc_idx] += q_idf * (numerator / denominator)

        # Pair scores with chunk objects
        scored_docs = [(self.chunks[i], scores[i]) for i in range(self.doc_count)]
        scored_docs.sort(key=lambda x: x[1], reverse=True)

        results = []
        for rank, (chunk, score) in enumerate(scored_docs[:top_k], start=1):
            results.append((chunk, score, rank))

        return results

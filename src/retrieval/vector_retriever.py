"""Dense Semantic Vector Store & Retriever.

Provides semantic dense embedding retrieval using term-weighted subword n-gram
projections and cosine similarity. Fully self-contained, deterministic, and fast.
"""

from typing import List, Tuple, Dict
import math
import re
from src.retrieval.document_indexer import DocumentChunk


def extract_features(text: str) -> Dict[str, float]:
    """Extracts word tokens and character 3-grams/4-grams for subword semantic representation."""
    features: Dict[str, float] = {}
    clean = text.lower()
    
    # Word unigrams
    words = re.findall(r"\b[\w-]+\b", clean)
    for w in words:
        features[f"w:{w}"] = features.get(f"w:{w}", 0.0) + 1.0

    # Character n-grams for typo and morphology tolerance
    for i in range(len(clean) - 2):
        tri = clean[i:i+3]
        if not tri.isspace():
            features[f"c3:{tri}"] = features.get(f"c3:{tri}", 0.0) + 0.5

    for i in range(len(clean) - 3):
        quad = clean[i:i+4]
        if not quad.isspace():
            features[f"c4:{quad}"] = features.get(f"c4:{quad}", 0.0) + 0.3

    return features


def l2_normalize(vec: Dict[str, float]) -> Dict[str, float]:
    """Normalizes vector to unit L2 norm."""
    norm = math.sqrt(sum(v * v for v in vec.values()))
    if norm == 0.0:
        return vec
    return {k: v / norm for k, v in vec.items()}


def cosine_similarity(v1: Dict[str, float], v2: Dict[str, float]) -> float:
    """Computes cosine similarity between two sparse/dense feature vectors."""
    # Iterate over smaller dictionary for speed
    if len(v1) > len(v2):
        v1, v2 = v2, v1
    dot_product = sum(val * v2.get(k, 0.0) for k, val in v1.items())
    return max(0.0, min(1.0, dot_product))


class DenseVectorRetriever:
    """Semantic Vector Indexer and Cosine Similarity Retriever."""

    def __init__(self):
        self.chunks: List[DocumentChunk] = []
        self.doc_vectors: List[Dict[str, float]] = []
        self.feature_idf: Dict[str, float] = {}

    def index(self, chunks: List[DocumentChunk]) -> None:
        """Embeds document chunks and indexes them."""
        self.chunks = chunks
        num_docs = len(chunks)
        raw_feature_counts: List[Dict[str, float]] = []
        doc_frequency: Dict[str, int] = {}

        for chunk in chunks:
            full_text = f"{chunk.doc_title}\n{chunk.section_title}\n{chunk.content}"
            feats = extract_features(full_text)
            raw_feature_counts.append(feats)
            for k in feats.keys():
                doc_frequency[k] = doc_frequency.get(k, 0) + 1

        # Calculate IDF for all features
        self.feature_idf = {}
        for feat, df in doc_frequency.items():
            idf = math.log((num_docs + 1.0) / (df + 1.0)) + 1.0
            self.feature_idf[feat] = idf

        # Build L2-normalized TF-IDF vectors
        self.doc_vectors = []
        for feats in raw_feature_counts:
            weighted = {k: v * self.feature_idf[k] for k, v in feats.items()}
            self.doc_vectors.append(l2_normalize(weighted))

    def retrieve(self, query: str, top_k: int = 5) -> List[Tuple[DocumentChunk, float, int]]:
        """Retrieves top_k chunks by semantic cosine similarity.
        
        Returns:
            List of tuples: (DocumentChunk, cosine_similarity_score, rank_1_indexed)
        """
        if not self.chunks:
            return []

        q_feats = extract_features(query)
        q_weighted = {k: v * self.feature_idf.get(k, 1.0) for k, v in q_feats.items()}
        q_norm = l2_normalize(q_weighted)

        scores: List[Tuple[DocumentChunk, float]] = []
        for idx, doc_vec in enumerate(self.doc_vectors):
            sim = cosine_similarity(q_norm, doc_vec)
            scores.append((self.chunks[idx], sim))

        scores.sort(key=lambda x: x[1], reverse=True)

        results = []
        for rank, (chunk, score) in enumerate(scores[:top_k], start=1):
            results.append((chunk, score, rank))

        return results

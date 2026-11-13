"""Multilingual Natural Language Processing modules for iCare."""

from src.nlp.language_detector import detect_language
from src.nlp.cross_lingual_normalizer import normalize_query, REGULATORY_CONCEPTS

__all__ = [
    "detect_language",
    "normalize_query",
    "REGULATORY_CONCEPTS"
]

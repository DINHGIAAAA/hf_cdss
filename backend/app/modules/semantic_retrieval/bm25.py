"""BM25 hybrid search for retrieval-time document matching."""

from __future__ import annotations

import logging
from collections import Counter
from math import log
from typing import Sequence

logger = logging.getLogger(__name__)


class BM25:
    """In-memory BM25 index for keyword-based document retrieval."""

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.documents: list[str] = []
        self.doc_ids: list[str] = []
        self.avgdl: float = 0.0
        self.doc_len: list[int] = []
        self.doc_freqs: list[dict[str, int]] = []
        self.idf: dict[str, float] = {}
        self._indexed = False

    def index(self, doc_ids: list[str], documents: list[str]) -> None:
        """Build BM25 index from documents."""
        self.doc_ids = doc_ids
        self.documents = documents
        self.doc_len = [len(doc.split()) for doc in documents]
        self.avgdl = sum(self.doc_len) / len(self.doc_len) if self.doc_len else 0

        # Calculate document frequencies
        self.doc_freqs = []
        for doc in documents:
            freq = Counter(doc.lower().split())
            self.doc_freqs.append(freq)

        # Calculate IDF
        N = len(documents)
        df = Counter()
        for freq in self.doc_freqs:
            for term in freq:
                df[term] += 1

        self.idf = {term: log((N - df[term] + 0.5) / (df[term] + 0.5) + 1) for term in df}
        self._indexed = True

        logger.info("BM25 indexed %d documents, vocabulary size: %d", N, len(self.idf))

    def search(self, query: str, top_k: int = 50) -> list[tuple[str, float]]:
        """Search documents by query, return (doc_id, score) pairs."""
        if not self._indexed:
            raise RuntimeError("BM25 index not built. Call index() first.")

        query_terms = query.lower().split()
        if not query_terms:
            return []

        scores: list[tuple[str, float]] = []
        for i, doc_freq in enumerate(self.doc_freqs):
            score = self._score(query_terms, doc_freq, self.doc_len[i])
            if score > 0:
                scores.append((self.doc_ids[i], score))

        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]

    def _score(self, query_terms: list[str], doc_freq: dict[str, int], doc_len: int) -> float:
        """Calculate BM25 score for a single document."""
        score = 0.0
        for term in query_terms:
            if term not in doc_freq:
                continue
            tf = doc_freq[term]
            idf = self.idf.get(term, 0)
            numerator = tf * (self.k1 + 1)
            denominator = tf + self.k1 * (1 - self.b + self.b * doc_len / self.avgdl)
            score += idf * numerator / denominator
        return score


# Global BM25 instance - lazily initialized
_bm25_index: BM25 | None = None
_bm25_doc_ids: list[str] = []
_bm25_doc_texts: list[str] = []


def build_bm25_index(documents: list[tuple[str, str]]) -> BM25:
    """Build BM25 index from (doc_id, text) pairs.

    Args:
        documents: List of (doc_id, text) tuples

    Returns:
        BM25 index ready for searching
    """
    doc_ids = [doc_id for doc_id, _ in documents]
    texts = [text for _, text in documents]

    index = BM25()
    index.index(doc_ids, texts)
    return index


def get_bm25_index() -> BM25 | None:
    """Get the cached BM25 index."""
    return _bm25_index


def clear_bm25_index() -> None:
    """Clear the cached BM25 index."""
    global _bm25_index, _bm25_doc_ids, _bm25_doc_texts
    _bm25_index = None
    _bm25_doc_ids = []
    _bm25_doc_texts = []

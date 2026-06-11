"""BM25 keyword search over locally cached chunks."""
from __future__ import annotations

import numpy as np

from app.ingestion.pipeline import load_bm25
from app.models.schemas import RecipeChunk


def keyword_search(query: str, top_k: int = 20) -> list[tuple[RecipeChunk, float]]:
    """
    BM25 search. Returns up to top_k (chunk, score) pairs.
    Scores are normalised to [0, 1] relative to the max score in this result set.
    """
    bm25, chunks = load_bm25()
    if not chunks:
        return []

    tokens = query.lower().split()
    scores = bm25.get_scores(tokens)

    if scores.max() == 0:
        return []

    top_indices = np.argsort(scores)[::-1][:top_k]
    max_score = float(scores.max())

    results = []
    for idx in top_indices:
        score = float(scores[idx])
        if score <= 0:
            break
        results.append((chunks[idx], score / max_score))

    return results

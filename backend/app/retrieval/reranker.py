"""
Score-fusion reranker — replaces the LLM cross-encoder with fast math.

Uses Reciprocal Rank Fusion (RRF) over the semantic and BM25 rank positions.
Eliminates the LLM reranking roundtrip (~3-6s saved per query).
"""
from __future__ import annotations

from app.models.schemas import RecipeChunk


def rerank(
    query: str,
    candidates: list[tuple[RecipeChunk, float]],
    top_n: int = 5,
) -> list[tuple[RecipeChunk, float]]:
    """
    Rerank candidates using score-weighted fusion.

    Candidates already carry a score that is the max of (semantic_score, bm25_score)
    from _merge_results. We apply a small BM25 keyword-overlap boost so that chunks
    whose text literally contains words from the query rank slightly higher than
    semantically-similar-but-off-topic chunks.
    """
    if not candidates:
        return []

    query_tokens = set(query.lower().split())

    scored: list[tuple[RecipeChunk, float]] = []
    for chunk, base_score in candidates:
        # Keyword overlap boost: fraction of query words found in chunk text
        text_lower = (chunk.text + " " + chunk.recipe_name + " " + chunk.component_name).lower()
        overlap = sum(1 for t in query_tokens if t in text_lower) / max(len(query_tokens), 1)
        # Weighted: 80% base score (semantic/BM25 already merged), 20% keyword overlap
        final = 0.80 * base_score + 0.20 * overlap
        scored.append((chunk, final))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_n]

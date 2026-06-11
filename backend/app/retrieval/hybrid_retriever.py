"""
Hybrid retriever: semantic (Pinecone) + BM25 keyword, fused with score-weighted reranking.

No LLM calls in this path — all fast, deterministic operations.
The recipe_finder's two-phase approach (search → load full recipe) handles completeness.
"""
from __future__ import annotations

from app.models.schemas import RecipeChunk
from app.retrieval.bm25_search import keyword_search
from app.retrieval.reranker import rerank
from app.retrieval.vector_store import semantic_search


def _merge_results(
    a: list[tuple[RecipeChunk, float]],
    b: list[tuple[RecipeChunk, float]],
) -> list[tuple[RecipeChunk, float]]:
    """Merge two ranked lists, deduplicating by chunk_id, keeping highest score."""
    seen: dict[str, tuple[RecipeChunk, float]] = {}
    for chunk, score in a + b:
        if chunk.chunk_id not in seen or score > seen[chunk.chunk_id][1]:
            seen[chunk.chunk_id] = (chunk, score)
    return list(seen.values())


def retrieve(
    query: str,
    top_k: int = 10,
) -> tuple[list[tuple[RecipeChunk, float]], float]:
    """
    Hybrid retrieve: semantic + BM25 merged, score-fused reranked.

    Returns:
        (results, confidence)
        results    — list of (RecipeChunk, relevance_score), up to top_k
        confidence — top score after reranking (0–1 proxy for match quality)
    """
    semantic = semantic_search(query, top_k=20)
    keyword = keyword_search(query, top_k=20)
    merged = _merge_results(semantic, keyword)
    reranked = rerank(query, merged, top_n=top_k)

    confidence = reranked[0][1] if reranked else 0.0
    return reranked, confidence


def retrieve_recipe_by_name(name: str) -> list[RecipeChunk]:
    """
    Fetch all components of a specific recipe by name.
    Used by scaling, indent, and anomaly tools that need full recipe data.
    """
    semantic = semantic_search(name, top_k=30)
    keyword = keyword_search(name, top_k=30)
    merged = _merge_results(semantic, keyword)

    name_lower = name.lower()
    matches = [
        chunk for chunk, _ in merged
        if name_lower in chunk.recipe_name.lower()
        or chunk.recipe_name.lower() in name_lower
    ]

    return matches if matches else [chunk for chunk, _ in merged[:10]]

"""Pinecone semantic search with Nebius embeddings."""
from __future__ import annotations

from openai import OpenAI
from pinecone import Pinecone

from app.config import settings
from app.models.schemas import RecipeChunk

# Module-level singletons — initialised once per process, reused across requests
_embed_client: OpenAI | None = None
_pc_index = None


def _get_embed_client() -> OpenAI:
    global _embed_client
    if _embed_client is None:
        _embed_client = OpenAI(
            api_key=settings.nebius_api_key,
            base_url=settings.nebius_base_url,
        )
    return _embed_client


def _get_pc_index():
    global _pc_index
    if _pc_index is None:
        pc = Pinecone(api_key=settings.pinecone_api_key)
        _pc_index = pc.Index(settings.pinecone_index_name)
    return _pc_index


def _embed(text: str) -> list[float]:
    resp = _get_embed_client().embeddings.create(
        model=settings.nebius_embedding_model,
        input=[text],
    )
    return resp.data[0].embedding


def semantic_search(query: str, top_k: int = 20) -> list[tuple[RecipeChunk, float]]:
    """
    Return up to top_k (chunk, score) pairs ordered by cosine similarity.
    """
    import json
    from app.models.schemas import Ingredient

    global _pc_index

    embedding = _embed(query)

    def _do_query():
        return _get_pc_index().query(
            vector=embedding,
            top_k=top_k,
            namespace=settings.pinecone_namespace,
            include_metadata=True,
        )

    try:
        resp = _do_query()
    except Exception:
        # Connection dropped — reset singleton and retry once
        _pc_index = None
        resp = _do_query()

    results: list[tuple[RecipeChunk, float]] = []
    for match in resp.matches:
        meta = match.metadata or {}
        try:
            ingredients = [
                Ingredient(**i)
                for i in json.loads(meta.get("ingredients_json", "[]"))
            ]
            method = json.loads(meta.get("method_json", "[]"))
        except Exception:
            ingredients, method = [], []

        chunk = RecipeChunk(
            chunk_id=match.id,
            source_file=meta.get("source_file", ""),
            recipe_name=meta.get("recipe_name", ""),
            recipe_number=meta.get("recipe_number", ""),
            component_name=meta.get("component_name", ""),
            yield_label=meta.get("yield_label", ""),
            total_g=float(meta.get("total_g", 0)),
            ingredients=ingredients,
            method=method,
            text=meta.get("text", ""),
        )
        results.append((chunk, float(match.score)))

    return results


def get_index_stats() -> dict:
    pc = Pinecone(api_key=settings.pinecone_api_key)
    index = pc.Index(settings.pinecone_index_name)
    stats = index.describe_index_stats()
    ns = stats.namespaces.get(settings.pinecone_namespace)
    return {
        "total_vectors": stats.total_vector_count,
        "namespace_vectors": ns.vector_count if ns else 0,
    }

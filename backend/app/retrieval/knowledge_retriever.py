"""
Semantic knowledge retriever — searches the `patisserie-semantic` Pinecone
namespace for general knowledge queries (technique explanations, baking science).

Separate from the hybrid retriever used for structured recipe lookup.
"""

from __future__ import annotations

from openai import OpenAI
from pinecone import Pinecone

from app.config import settings

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


def search_knowledge(query: str, top_k: int = 5) -> list[dict]:
    """
    Search the semantic namespace. Returns a list of dicts:
      { text, source_file, page, score }
    sorted by relevance descending.
    """
    resp = _get_embed_client().embeddings.create(
        model=settings.nebius_embedding_model,
        input=[query],
    )
    embedding = resp.data[0].embedding

    index = _get_pc_index()
    result = index.query(
        vector=embedding,
        top_k=top_k,
        namespace=settings.pinecone_semantic_namespace,
        include_metadata=True,
    )

    chunks = []
    for match in result.matches:
        meta = match.metadata or {}
        chunks.append({
            "text": meta.get("text", ""),
            "source_file": meta.get("source_file", ""),
            "page": int(meta.get("page", 0)),
            "score": float(match.score),
        })

    return chunks

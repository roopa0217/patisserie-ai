"""
Ingestion pipeline — idempotent.

Workflow for a single PDF:
  1. Parse PDF → list[RecipeChunk]
  2. Embed each chunk via Nebius
  3. Upsert to Pinecone (chunk_id is the vector ID — same file re-ingested
     overwrites, never duplicates)
  4. Rebuild the BM25 index from all stored chunk texts
"""

from __future__ import annotations

import json
import pickle
from pathlib import Path

from openai import OpenAI
from pinecone import Pinecone
from rank_bm25 import BM25Okapi

from app.config import settings
from app.ingestion.pdf_parser import parse_pdf
from app.ingestion.semantic_chunker import create_semantic_chunks
from app.models.schemas import RecipeChunk


# ── Embedding client (Nebius, OpenAI-compatible) ──────────────────────────────

def _get_embed_client() -> OpenAI:
    return OpenAI(
        api_key=settings.nebius_api_key,
        base_url=settings.nebius_base_url,
    )


def _embed_texts(texts: list[str]) -> list[list[float]]:
    client = _get_embed_client()
    response = client.embeddings.create(
        model=settings.nebius_embedding_model,
        input=texts,
    )
    return [item.embedding for item in response.data]


# ── Pinecone ──────────────────────────────────────────────────────────────────

def _get_index():
    pc = Pinecone(api_key=settings.pinecone_api_key)
    return pc.Index(settings.pinecone_index_name)


def _delete_vectors_for_file(source_file: str) -> None:
    """Delete structured + semantic vectors for source_file before re-ingestion."""
    index = _get_index()
    for ns in (settings.pinecone_namespace, settings.pinecone_semantic_namespace):
        try:
            index.delete(
                filter={"source_file": {"$eq": source_file}},
                namespace=ns,
            )
        except Exception:
            pass


def _upsert_semantic_chunks(pdf_path: Path) -> None:
    """Embed page-level chunks and upsert to the semantic namespace."""
    chunks = create_semantic_chunks(pdf_path)
    if not chunks:
        return

    texts = [c["text"] for c in chunks]
    client = OpenAI(api_key=settings.nebius_api_key, base_url=settings.nebius_base_url)
    response = client.embeddings.create(model=settings.nebius_embedding_model, input=texts)
    embeddings = [item.embedding for item in response.data]

    index = _get_index()
    vectors = []
    for chunk, emb in zip(chunks, embeddings):
        vectors.append({
            "id": chunk["chunk_id"],
            "values": emb,
            "metadata": {
                "text": chunk["text"][:1200],
                "source_file": chunk["source_file"],
                "page": chunk["page"],
            },
        })

    for i in range(0, len(vectors), 100):
        index.upsert(vectors=vectors[i:i + 100], namespace=settings.pinecone_semantic_namespace)


def _upsert_chunks(chunks: list[RecipeChunk]) -> None:
    if not chunks:
        return
    _delete_vectors_for_file(chunks[0].source_file)
    index = _get_index()
    texts = [c.text for c in chunks]
    embeddings = _embed_texts(texts)

    vectors = []
    for chunk, embedding in zip(chunks, embeddings):
        vectors.append({
            "id": chunk.chunk_id,
            "values": embedding,
            "metadata": {
                "source_file": chunk.source_file,
                "recipe_name": chunk.recipe_name,
                "recipe_number": chunk.recipe_number,
                "component_name": chunk.component_name,
                "yield_label": chunk.yield_label,
                "total_g": chunk.total_g,
                # Cap ingredients at 30 items; method is in text already
                "ingredients_json": json.dumps(
                    [i.model_dump() for i in chunk.ingredients[:30]]
                ),
                # First 2 method steps only — full method is reconstructable from text
                "method_json": json.dumps(chunk.method[:2]),
                # Keep text lean; full text lives in BM25 cache
                "text": chunk.text[:800],
                "parent_section": chunk.parent_section,
            },
        })

    # Upsert in batches of 100
    for i in range(0, len(vectors), 100):
        index.upsert(
            vectors=vectors[i:i + 100],
            namespace=settings.pinecone_namespace,
        )


# ── BM25 index (local, rebuilt after every ingestion) ────────────────────────

_BM25_PATH = Path(settings.bm25_index_path)
_CHUNKS_STORE_PATH = Path(settings.bm25_index_path).parent / "chunks_store.json"


def _tokenise(text: str) -> list[str]:
    return text.lower().split()


def _save_chunks_store(chunks: list[RecipeChunk]) -> None:
    """Persist full-text chunks locally so BM25 never relies on Pinecone's truncated metadata.
    Removes all previous entries for the same source_file before writing new ones so stale
    chunks from earlier parser runs don't persist after re-ingestion."""
    _CHUNKS_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    existing: dict[str, dict] = {}
    if _CHUNKS_STORE_PATH.exists():
        with open(_CHUNKS_STORE_PATH) as f:
            existing = json.load(f)

    if chunks:
        source_file = chunks[0].source_file
        existing = {k: v for k, v in existing.items() if v.get("source_file") != source_file}

    for c in chunks:
        existing[c.chunk_id] = c.model_dump()
    with open(_CHUNKS_STORE_PATH, "w") as f:
        json.dump(existing, f)


def _load_chunks_store() -> list[RecipeChunk]:
    if not _CHUNKS_STORE_PATH.exists():
        return []
    with open(_CHUNKS_STORE_PATH) as f:
        data = json.load(f)
    return [RecipeChunk(**v) for v in data.values()]


def rebuild_bm25(all_chunks: list[RecipeChunk]) -> None:
    if not all_chunks:
        return
    corpus = [_tokenise(c.text) for c in all_chunks]
    index = BM25Okapi(corpus)
    _BM25_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_BM25_PATH, "wb") as f:
        pickle.dump({"index": index, "chunks": all_chunks}, f)


def load_bm25() -> tuple[BM25Okapi, list[RecipeChunk]]:
    if not _BM25_PATH.exists():
        return BM25Okapi([[]]), []
    with open(_BM25_PATH, "rb") as f:
        data = pickle.load(f)
    return data["index"], data["chunks"]


# ── Fetch all stored chunks from Pinecone (for BM25 rebuild) ─────────────────

def fetch_all_chunks() -> list[RecipeChunk]:
    """
    Pull every vector's metadata from Pinecone and reconstruct RecipeChunk
    objects. Used after upsert to rebuild the BM25 index.
    """
    from app.models.schemas import Ingredient

    index = _get_index()
    results: list[RecipeChunk] = []
    pagination_token = None

    while True:
        kwargs: dict = {
            "namespace": settings.pinecone_namespace,
            "limit": 100,
            "include_metadata": True,
        }
        if pagination_token:
            kwargs["pagination_token"] = pagination_token

        response = index.list_paginated(**kwargs)
        ids = [v.id for v in response.vectors] if hasattr(response, "vectors") else []

        if ids:
            fetch_resp = index.fetch(ids=ids, namespace=settings.pinecone_namespace)
            for vid, vec in fetch_resp.vectors.items():
                meta = vec.metadata or {}
                try:
                    ingredients = [
                        Ingredient(**i)
                        for i in json.loads(meta.get("ingredients_json", "[]"))
                    ]
                    method = json.loads(meta.get("method_json", "[]"))
                except Exception:
                    ingredients, method = [], []

                results.append(
                    RecipeChunk(
                        chunk_id=vid,
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
                )

        next_token = getattr(response, "pagination", None)
        if next_token and hasattr(next_token, "next"):
            pagination_token = next_token.next
        else:
            break

    return results


# ── Public entry point ────────────────────────────────────────────────────────

def ingest_pdf(pdf_path: str | Path) -> dict:
    """
    Parse, embed, and upsert a single PDF. Returns a summary dict.
    Idempotent: re-ingesting the same file updates existing vectors in Pinecone
    and the local chunk store.
    """
    pdf_path = Path(pdf_path)
    chunks = parse_pdf(pdf_path)
    if not chunks:
        return {"file": pdf_path.name, "chunks": 0, "status": "no_chunks_found"}

    # 1. Embed and upsert structured chunks to Pinecone (recipe search namespace)
    _upsert_chunks(chunks)

    # 2. Embed and upsert semantic chunks to Pinecone (AI assistant namespace)
    _upsert_semantic_chunks(pdf_path)

    # 3. Persist full-text structured chunks locally (for BM25)
    _save_chunks_store(chunks)

    # 4. Rebuild BM25 from the local store
    all_chunks = _load_chunks_store()
    rebuild_bm25(all_chunks)

    # 5. Invalidate the recipe_finder in-memory cache
    from app.tools.recipe_finder import invalidate_cache
    invalidate_cache()

    return {
        "file": pdf_path.name,
        "chunks": len(chunks),
        "semantic_chunks": len(create_semantic_chunks(pdf_path)),
        "recipes": len({c.recipe_name for c in chunks if c.recipe_name}),
        "status": "ok",
    }

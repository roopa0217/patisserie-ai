from __future__ import annotations

import json
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

import difflib

from app.agent.graph import run_agent_stream
from app.ingestion.pipeline import ingest_pdf, load_bm25
from app.models.schemas import ChatRequest
from app.retrieval.vector_store import get_index_stats
from app.tools.recipe_finder import _load_by_recipe

app = FastAPI(title="Pâtisserie AI", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


# ── Stats (sidebar live counters) ─────────────────────────────────────────────

@app.get("/stats")
def stats():
    try:
        vs = get_index_stats()
        _, chunks = load_bm25()
        return {
            "pinecone_vectors": vs.get("namespace_vectors", 0),
            "bm25_chunks": len(chunks),
        }
    except Exception as e:
        return {"pinecone_vectors": 0, "bm25_chunks": 0, "error": str(e)}


# ── PDF Upload & Ingestion ────────────────────────────────────────────────────

@app.post("/ingest/upload")
async def upload_pdf(file: UploadFile = File(...)):
    """
    Accept a PDF upload, parse it, embed each component chunk, and upsert
    to Pinecone. Idempotent — re-uploading the same file updates existing vectors.
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        # Override the temp filename with the original so chunk IDs are stable
        tmp_path = tmp_path.rename(tmp_path.parent / file.filename)
        result = ingest_pdf(tmp_path)
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass

    return result


# ── Recipe Search (direct, no LLM) ───────────────────────────────────────────

def _recipe_name_search(q: str, by_recipe: dict) -> list[str]:
    """
    Name-only search: no semantic fallback, no hallucination.

    Three passes:
      1. Exact word match against recipe name.
      2. Fuzzy match against recipe name (handles minor typos, cutoff 0.82).
      3. Component name match — query words found in a component name;
         returns the parent recipe so the full recipe is shown.

    Returns an empty list when nothing genuinely matches.
    """
    q_words = q.lower().split()
    names = [n for n in by_recipe if n]

    # Pass 1: every query word appears verbatim in the recipe name
    exact = [
        n for n in names
        if all(w in n.lower() for w in q_words)
    ]
    if exact:
        return exact

    # Pass 2: fuzzy — each query word must closely match at least one name word
    def _word_matches(q_word: str, name: str) -> bool:
        return any(
            difflib.SequenceMatcher(None, q_word, nw).ratio() >= 0.82
            for nw in name.lower().split()
        )

    fuzzy = [
        n for n in names
        if all(_word_matches(w, n) for w in q_words)
    ]
    if fuzzy:
        return fuzzy

    # Pass 3: search component names — return the parent recipe
    seen: set[str] = set()
    component_hits: list[str] = []
    for recipe_name, chunks in by_recipe.items():
        if recipe_name in seen:
            continue
        for chunk in chunks:
            comp = chunk.component_name.lower()
            if all(w in comp for w in q_words):
                component_hits.append(recipe_name)
                seen.add(recipe_name)
                break
    return component_hits


@app.get("/recipes/search")
def recipe_search(q: str = ""):
    """
    Direct recipe lookup from the structured chunk store — no LLM, no semantic search.
    Returns only genuine name matches (exact or minor typo). Never returns unrelated recipes.
    """
    if not q.strip():
        by_recipe = _load_by_recipe()
        names = sorted(n for n in by_recipe if n)
        return {"query": "", "recipes": [], "all_names": names}

    by_recipe = _load_by_recipe()
    matched = _recipe_name_search(q, by_recipe)

    if not matched:
        return {"query": q, "recipes": [], "all_names": []}

    # Section expansion: also include sibling recipes whose parent_section shares
    # a keyword with a matched recipe name (e.g. "Berliner Variations" ↔ "Doughnut / Berliner")
    _STOP = {"and", "with", "the", "for", "from"}
    anchor_words = {w.lower() for n in matched for w in n.split() if len(w) > 3 and w.lower() not in _STOP}
    matched_set = set(matched)
    for name, chunks in by_recipe.items():
        if name in matched_set:
            continue
        for c in chunks:
            if c.parent_section and any(word in c.parent_section.lower() for word in anchor_words):
                matched.append(name)
                matched_set.add(name)
                break

    from collections import defaultdict
    by_recipe_chunks: dict = defaultdict(list)
    for name in matched:
        for c in by_recipe.get(name, []):
            by_recipe_chunks[c.recipe_name].append(c)

    recipes_out = []
    for name in matched:
        recipe_chunks = by_recipe_chunks.get(name, [])
        if not recipe_chunks:
            continue
        components = []
        for c in recipe_chunks:
            components.append({
                "component_name": c.component_name,
                "yield_label": c.yield_label,
                "ingredients": [{"name": i.name, "qty_g": i.qty_g, "pct": i.pct} for i in c.ingredients],
                "total_g": c.total_g,
                "method": c.method,
                "method_raw": c.method_raw,
            })
        recipes_out.append({
            "recipe_name": name,
            "source_file": recipe_chunks[0].source_file,
            "section": recipe_chunks[0].parent_section or "",
            "components": components,
        })

    return {"query": q, "recipes": recipes_out, "all_names": []}


# ── Chat (streaming SSE) ──────────────────────────────────────────────────────

@app.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """
    Stream the agent's response as Server-Sent Events.

    Event types emitted:
      data: {"type": "status",  "content": "..."}
      data: {"type": "token",   "content": "..."}
      data: {"type": "result",  "content": {...}}
      data: {"type": "meta",    "content": {"confidence": 0.87, "sources": [...]}}
      data: {"type": "done"}
    """
    history = [m.model_dump() for m in request.history]

    async def generate():
        try:
            async for event in run_agent_stream(request.message, history):
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )

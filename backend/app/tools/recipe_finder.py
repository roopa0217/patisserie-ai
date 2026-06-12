"""
Find recipes from the knowledge base.

Two-phase approach:
  Phase 1 — use hybrid search to identify which recipe names match the query
  Phase 2 — load EVERY chunk for those recipe names from the local store

This guarantees complete recipes (all components) rather than truncated top-k results.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

from app.config import settings
from app.models.schemas import RecipeChunk
from app.retrieval.hybrid_retriever import retrieve

CONFIDENCE_THRESHOLD = 0.30
MAX_RECIPES = 5          # show up to this many distinct recipes per query

# Bad-name tokens — chunks whose recipe_name looks like a method step, not a recipe
_BAD_NAME_TOKENS = frozenset([
    " aside", " till ", "before use", "as required", " further ",
    "melted ", "and set", "till smooth", "to a smooth",
])
_BAD_NAME_VERBS = re.compile(
    r"^(mix|add|bake|heat|pour|combine|cut|brush|cook|roll|fold|whisk|melt|"
    r"cool|chill|fry|boil|simmer|stir|transfer|place|allow|remove|prepare|"
    r"knead|shape|pipe|fill|coat|drain|use|apply|make|set|let|leave|check|"
    r"warm|whip|season|cream\s|blitz|sheet|smooth|emulsify|temper|dry\s|"
    r"lastly|then\s|keep|glaze|sieve|sift|grate|chop|slice|garnish|serve|"
    r"refrigerate|freeze|thaw|sprinkle|dust|press|trim|decorate|infuse|"
    r"strain|pass|weigh|portion|line|grease|spread|flatten|wrap|seal)",
    re.IGNORECASE,
)


def _is_bad_recipe_name(name: str) -> bool:
    """Return True for chunks that were mis-parsed as recipes (method steps, section headers)."""
    if not name or len(name) < 3:
        return True
    low = name.lower()
    if any(tok in low for tok in _BAD_NAME_TOKENS):
        return True
    if _BAD_NAME_VERBS.match(name):
        return True
    if len(name.split()) >= 7:
        return True
    return False
_STORE_PATH = Path(settings.bm25_index_path).parent / "chunks_store.json"

# In-memory cache so we don't reload the file on every request
_chunk_cache: dict[str, list[RecipeChunk]] | None = None


def _load_by_recipe() -> dict[str, list[RecipeChunk]]:
    """Return chunks_store grouped by recipe_name, cached in memory."""
    global _chunk_cache
    if _chunk_cache is not None:
        return _chunk_cache

    if not _STORE_PATH.exists():
        return {}

    with open(_STORE_PATH) as f:
        raw = json.load(f)

    data = raw.values() if isinstance(raw, dict) else raw
    by_recipe: dict[str, list[RecipeChunk]] = defaultdict(list)
    for item in data:
        chunk = RecipeChunk(**item)
        by_recipe[chunk.recipe_name].append(chunk)

    _chunk_cache = dict(by_recipe)
    return _chunk_cache


def invalidate_cache() -> None:
    """Call this after ingestion so the next request reloads the store."""
    global _chunk_cache
    _chunk_cache = None


def find_recipes(query: str, restrict_to_name: str | None = None) -> dict:
    """
    Phase 1: hybrid search → ranked list of matching recipe names.
    Phase 2: load all chunks for those recipes from the local store.

    restrict_to_name — when set, only return recipes whose name contains this
    string (case-insensitive).  Used when the query quotes a specific recipe so
    semantically-similar-but-wrong recipes don't sneak into the results.

    Returns:
        {
            "chunks": list[RecipeChunk],   # complete components for each matched recipe
            "matched_recipes": list[str],  # ordered list of matched recipe names
            "confidence": float,
            "low_confidence": bool,
        }
    """
    # ── Phase 1: identify matching recipes ───────────────────────────────────
    results, confidence = retrieve(query, top_k=20)

    if not results or confidence < CONFIDENCE_THRESHOLD:
        return {
            "chunks": [],
            "matched_recipes": [],
            "confidence": confidence,
            "low_confidence": True,
        }

    # Rank recipes by their best matching chunk score
    recipe_best_score: dict[str, float] = {}
    for chunk, score in results:
        name = chunk.recipe_name
        if name not in recipe_best_score or score > recipe_best_score[name]:
            recipe_best_score[name] = score

    top_score = max(recipe_best_score.values(), default=0.0)
    # Drop recipes whose best score is below 80% of the top score — prevents
    # generic names like "Tarts" sneaking in alongside specific matches.
    MIN_RELATIVE_SCORE = 0.80

    restrict_lower = restrict_to_name.lower() if restrict_to_name else None

    _STOP_WORDS = {"and", "&", "the", "a", "an", "of", "with", "for", "in", "de"}

    def _name_matches_restriction(name: str) -> bool:
        if restrict_lower is None:
            return True
        n = name.lower()
        # Exact containment: restriction is fully inside the candidate name
        if restrict_lower in n:
            return True
        # Word-overlap: ≥75% of the significant restriction words must appear in the candidate.
        # This prevents short generic words like "tart" from matching unrelated recipes.
        r_words = {w for w in restrict_lower.split() if w not in _STOP_WORDS}
        n_words = {w for w in n.split() if w not in _STOP_WORDS}
        if not r_words:
            return True
        overlap = len(r_words & n_words) / len(r_words)
        return overlap >= 0.75

    ranked_recipes = sorted(
        (name for name, score in recipe_best_score.items()
         if score >= top_score * MIN_RELATIVE_SCORE
         and not _is_bad_recipe_name(name)
         and _name_matches_restriction(name)),
        key=recipe_best_score.get,  # type: ignore[arg-type]
        reverse=True,
    )
    top_recipes = ranked_recipes[:MAX_RECIPES]

    # ── Phase 2: load ALL components for each matched recipe ─────────────────
    by_recipe = _load_by_recipe()
    all_chunks: list[RecipeChunk] = []
    matched: list[str] = []
    for recipe_name in top_recipes:
        recipe_chunks = by_recipe.get(recipe_name, [])
        if recipe_chunks:
            all_chunks.extend(recipe_chunks)
            matched.append(recipe_name)

    if not matched:
        return {
            "chunks": [],
            "matched_recipes": [],
            "confidence": confidence,
            "low_confidence": True,
        }

    # ── Phase 2.5: section expansion ─────────────────────────────────────────
    # Include sibling recipes from the same section, matched two ways:
    #   1. Exact: another recipe has the same parent_section value
    #   2. Keyword: another recipe's parent_section shares a significant word with
    #      a matched recipe name (e.g. "Berliner Variations" ↔ "Doughnut / Berliner")
    matched_set = set(matched)
    sections_seen: set[str] = set()
    for chunks in [by_recipe.get(r, []) for r in matched]:
        for c in chunks:
            if c.parent_section:
                sections_seen.add(c.parent_section)

    # Significant words from matched recipe names (length > 3, lowercased)
    _STOP = {"and", "with", "the", "for", "from"}
    anchor_words: set[str] = set()
    for name in matched:
        anchor_words.update(
            w.lower() for w in name.split() if len(w) > 3 and w.lower() not in _STOP
        )

    def _section_matches(section: str) -> bool:
        if section in sections_seen:
            return True
        low = section.lower()
        return any(word in low for word in anchor_words)

    for recipe_name, chunks in by_recipe.items():
        if recipe_name in matched_set:
            continue
        if any(c.parent_section and _section_matches(c.parent_section) for c in chunks):
            all_chunks.extend(chunks)
            matched.append(recipe_name)
            matched_set.add(recipe_name)

    return {
        "chunks": all_chunks,
        "matched_recipes": matched,
        "confidence": confidence,
        "low_confidence": False,
    }

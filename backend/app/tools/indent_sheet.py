"""
Indent sheet builder — consolidates ingredients across multiple recipes
into one categorised ordering sheet. Deterministic arithmetic only.
"""
from __future__ import annotations

import re
from collections import defaultdict

from app.models.schemas import IndentRow, IndentSheet, RecipeChunk
from app.retrieval.hybrid_retriever import retrieve_recipe_by_name

# ── Ingredient categorisation ─────────────────────────────────────────────────

_CATEGORY_MAP: list[tuple[str, list[str]]] = [
    ("Chocolate & Cocoa", [
        "chocolate", "cocoa", "cacao", "couverture", "ganache",
    ]),
    ("Setting Agents", [
        "gelatin", "gelatine", "pectin", "agar", "carrageenan",
    ]),
    ("Dairy", [
        "cream", "milk", "butter", "mascarpone", "cheese", "yogurt",
        "fromage", "creme fraiche", "crème fraîche",
    ]),
    ("Eggs", [
        "egg", "yolk", "white", "albumen",
    ]),
    ("Dry Goods & Flour", [
        "flour", "starch", "cornflour", "cornstarch", "almond flour",
        "almond powder", "hazelnut flour", "baking powder", "baking soda",
        "bicarbonate", "gluten", "improver", "milk powder",
    ]),
    ("Sugar & Sweeteners", [
        "sugar", "glucose", "treacle", "honey", "invert sugar",
        "dextrose", "sorbitol", "icing", "fondant",
    ]),
    ("Fruit & Purees", [
        "puree", "purée", "fruit", "berry", "raspberry", "mango",
        "passion", "lemon", "lime", "orange", "apple", "banana",
        "strawberry", "confit",
    ]),
    ("Nuts & Seeds", [
        "hazelnut", "almond", "pistachio", "walnut", "pecan",
        "praline", "sesame", "seed",
    ]),
    ("Fats & Oils", [
        "oil", "shortening", "lard", "margarine",
    ]),
    ("Flavourings & Spices", [
        "vanilla", "coffee", "espresso", "cinnamon", "ginger",
        "cardamom", "rum", "liqueur", "extract", "zest", "salt",
    ]),
    ("Leavening & Yeast", [
        "yeast", "sourdough",
    ]),
]


def _categorise(ingredient_name: str) -> str:
    low = ingredient_name.lower()
    for category, keywords in _CATEGORY_MAP:
        if any(kw in low for kw in keywords):
            return category
    return "Other"


def _normalise_name(name: str) -> str:
    """Lower-case, strip trailing descriptors for aggregation."""
    name = name.lower().strip()
    # Remove parenthetical notes: "Butter, Cold-Diced" → "butter"
    name = re.sub(r",.*$", "", name).strip()
    return name


# ── Main tool ─────────────────────────────────────────────────────────────────

def build_indent_sheet(
    recipe_targets: list[dict],
) -> dict:
    """
    Build a consolidated indent sheet.

    Args:
        recipe_targets: List of {"recipe_name": str, "target_yield_g": float}
                        target_yield_g is optional; if omitted, base yield is used.

    Returns dict with IndentSheet or error.
    """
    if not recipe_targets:
        return {"error": True, "message": "No recipes specified."}

    # Accumulate: normalised_name → {category, total_g, sources}
    aggregated: dict[str, dict] = defaultdict(
        lambda: {"category": "Other", "total_g": 0.0, "sources": set()}
    )

    missing: list[str] = []

    for entry in recipe_targets:
        recipe_name = entry.get("recipe_name", "")
        target_yield = entry.get("target_yield_g")

        chunks = retrieve_recipe_by_name(recipe_name)
        structured = [c for c in chunks if c.ingredients]

        if not structured:
            missing.append(recipe_name)
            continue

        # Determine scale factor
        total_base = sum(c.total_g for c in structured if c.total_g)
        scale_factor = 1.0
        if target_yield and total_base:
            scale_factor = target_yield / total_base

        for chunk in structured:
            chunk_base = chunk.total_g or 1.0
            chunk_factor = (
                (target_yield / chunk_base) if target_yield and chunk.total_g
                else scale_factor
            )
            source_label = f"{recipe_name} / {chunk.component_name}"

            for ing in chunk.ingredients:
                scaled_qty = ing.qty_g * chunk_factor
                key = _normalise_name(ing.name)
                aggregated[key]["category"] = _categorise(ing.name)
                aggregated[key]["total_g"] += scaled_qty
                aggregated[key]["sources"].add(source_label)

    if not aggregated and missing:
        return {
            "error": True,
            "message": (
                f"None of the requested recipes were found: {', '.join(missing)}. "
                "Please upload the relevant PDFs first."
            ),
        }

    rows: list[IndentRow] = []
    for norm_name, data in aggregated.items():
        rows.append(
            IndentRow(
                ingredient=norm_name,
                category=data["category"],
                total_qty_g=round(data["total_g"], 1),
                sources=sorted(data["sources"]),
            )
        )

    # Sort by category then name
    rows.sort(key=lambda r: (r.category, r.ingredient))

    return {
        "error": False,
        "indent_sheet": IndentSheet(
            recipes=[e["recipe_name"] for e in recipe_targets],
            rows=rows,
        ),
        "missing_recipes": missing,
    }

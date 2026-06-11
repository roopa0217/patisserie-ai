"""
Yield scaler — deterministic arithmetic only, no LLM.

Non-linear ingredients (yeast, gelatin, baking powder, baking soda, salt)
scale sub-linearly at professional scale. The system applies a dampening
factor and always surfaces a warning for the instructor to verify.
"""
from __future__ import annotations

from app.models.schemas import Ingredient, RecipeChunk, ScaledIngredient, ScaleResult
from app.retrieval.hybrid_retriever import retrieve_recipe_by_name

# Dampening factors for non-linear ingredients (industry rule of thumb)
NON_LINEAR = {
    "yeast": 0.85,
    "gelatin": 0.90,
    "gelatine": 0.90,
    "baking powder": 0.85,
    "baking soda": 0.85,
    "bicarbonate of soda": 0.85,
    "salt": 0.90,
}

CONFIDENCE_THRESHOLD = 0.0  # scaler always proceeds if recipe found


def _is_non_linear(ingredient_name: str) -> tuple[bool, float]:
    low = ingredient_name.lower()
    for key, factor in NON_LINEAR.items():
        if key in low:
            return True, factor
    return False, 1.0


def scale_recipe(
    recipe_name: str,
    target_yield: float = 0.0,
    component_name: str | None = None,
    portions: int | None = None,
    portion_size_g: float | None = None,
    multiplier: float | None = None,
) -> dict:
    """
    Scale a recipe. Accepts three modes:

    1. Weight target:   target_yield=2000  → scale to 2000g total
    2. Portion-count:   portions=4, portion_size_g=50  → target = 4 × 50 = 200g
    3. Multiplier:      multiplier=2  → double every ingredient

    component_name optionally restricts to one component.
    """
    chunks = retrieve_recipe_by_name(recipe_name)
    if not chunks:
        return {
            "error": True,
            "message": f"Recipe '{recipe_name}' not found in the knowledge base.",
        }

    # Filter to components with structured ingredients
    structured = [c for c in chunks if c.ingredients]
    if not structured:
        return {
            "error": True,
            "message": (
                f"Recipe '{recipe_name}' was found but its ingredient data is not "
                "structured enough to scale. Check that the PDF was ingested correctly."
            ),
        }

    if component_name:
        target_comp = component_name.lower()
        structured = [
            c for c in structured
            if target_comp in c.component_name.lower()
        ]
        if not structured:
            return {
                "error": True,
                "message": (
                    f"Component '{component_name}' not found in recipe '{recipe_name}'."
                ),
            }

    scale_results = []
    all_warnings: list[str] = []

    # When a weight target is given without a specific component, the target is
    # the total assembled recipe weight.  Compute one shared factor so all
    # components are scaled proportionally (e.g. 700g / 1378g total = ×0.508).
    whole_recipe_factor: float | None = None
    if target_yield > 0 and component_name is None and multiplier is None and portions is None:
        total_base = sum(c.total_g for c in structured if c.total_g > 0)
        if total_base > 0:
            whole_recipe_factor = target_yield / total_base

    for chunk in structured:
        base_yield = chunk.total_g
        if base_yield <= 0:
            continue

        # Resolve the effective target weight for this component
        if whole_recipe_factor is not None:
            # Whole-recipe mode: same factor across every component
            scale_factor = whole_recipe_factor
            effective_target = round(base_yield * scale_factor, 1)
        elif portions is not None and portion_size_g is not None:
            effective_target = portions * portion_size_g
            scale_factor = effective_target / base_yield
        elif portions is not None:
            # portions-only: treat as multiplier against base yield
            effective_target = base_yield * portions
            scale_factor = effective_target / base_yield
        elif multiplier is not None:
            effective_target = base_yield * multiplier
            scale_factor = effective_target / base_yield
        else:
            effective_target = target_yield
            scale_factor = effective_target / base_yield
        scaled_ings: list[ScaledIngredient] = []
        component_warnings: list[str] = []

        for ing in chunk.ingredients:
            nl, factor = _is_non_linear(ing.name)
            effective_factor = scale_factor * factor if nl else scale_factor
            scaled_qty = round(ing.qty_g * effective_factor, 1)

            if nl:
                msg = (
                    f"⚠ {ing.name} in '{chunk.component_name}': scaled with "
                    f"dampening factor {factor} (non-linear ingredient). "
                    f"Verify the quantity {scaled_qty}g before production."
                )
                component_warnings.append(msg)
                all_warnings.append(msg)

            scaled_ings.append(
                ScaledIngredient(
                    name=ing.name,
                    original_qty_g=ing.qty_g,
                    scaled_qty_g=scaled_qty,
                    non_linear_warning=nl,
                )
            )

        scale_results.append(
            ScaleResult(
                recipe_name=chunk.recipe_name,
                component_name=chunk.component_name,
                original_yield=base_yield,
                target_yield=effective_target,
                scale_factor=round(scale_factor, 4),
                scaled_ingredients=scaled_ings,
                warnings=component_warnings,
            )
        )

    return {
        "error": False,
        "scale_results": scale_results,
        "global_warnings": all_warnings,
        "source_chunks": structured,
    }

"""
Anomaly checker — flags ingredients whose gram quantity exceeds defined thresholds.

Rules are defined in data/thresholds.json as {min_g, max_g} per ingredient.
No ratio calculation — the raw gram quantity is compared directly.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.config import settings
from app.models.schemas import AnomalyReport, AnomalyResult
from app.retrieval.hybrid_retriever import retrieve_recipe_by_name


def _load_rules() -> list[dict]:
    path = Path(settings.thresholds_path)
    if not path.exists():
        return []
    with open(path) as f:
        data = json.load(f)
    return data.get("rules", [])


def _matches(ingredient_name: str, rule: dict) -> bool:
    low = ingredient_name.lower()
    if rule["ingredient"].lower() in low:
        return True
    return any(alias.lower() in low for alias in rule.get("ingredient_aliases", []))


def check_anomalies(recipe_name: str) -> dict:
    """
    Check every component of a recipe against threshold rules.
    Flags any ingredient whose gram quantity exceeds max_g or falls below min_g.
    """
    rules = _load_rules()
    if not rules:
        return {"error": True, "message": "No threshold rules loaded."}

    chunks = retrieve_recipe_by_name(recipe_name)
    structured = [c for c in chunks if c.ingredients]

    if not structured:
        return {
            "error": True,
            "message": (
                f"Recipe '{recipe_name}' not found or has no structured ingredient data."
            ),
        }

    results: list[AnomalyResult] = []

    for chunk in structured:
        for rule in rules:
            min_g = rule.get("min_g", 0.0)
            max_g = rule.get("max_g", float("inf"))

            for ing in chunk.ingredients:
                if not _matches(ing.name, rule):
                    continue

                passed = min_g <= ing.qty_g <= max_g
                results.append(
                    AnomalyResult(
                        ingredient=ing.name,
                        component=chunk.component_name,
                        recipe=chunk.recipe_name,
                        actual_g=ing.qty_g,
                        min_g=min_g,
                        max_g=max_g,
                        passed=passed,
                        advice=rule.get("advice", "") if not passed else "",
                    )
                )

    if not results:
        return {
            "error": False,
            "message": (
                f"No threshold-checked ingredients found in '{recipe_name}'."
            ),
            "anomaly_report": AnomalyReport(
                recipe_name=recipe_name,
                results=[],
                overall_pass=True,
            ),
        }

    overall_pass = all(r.passed for r in results)

    return {
        "error": False,
        "anomaly_report": AnomalyReport(
            recipe_name=recipe_name,
            results=results,
            overall_pass=overall_pass,
        ),
    }

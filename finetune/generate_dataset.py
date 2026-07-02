"""
Generates a labeled training set for the custom intent-classifier fine-tune
(Llama-3.2-1B, LoRA + sequence-classification head -- see finetune/train_classifier.ipynb).

This is training data, NOT the eval set: evals/golden_dataset.csv stays held-out
and untouched. Any row here that exact-matches a golden_dataset.csv row is
dropped to avoid train/eval leakage.

Templates deliberately include the "hard" patterns already documented in
scripts/eval_intent_classifier.py's FAILURE_CLUSTERS (keyword bleed, double-check
idiom, portions-vs-lookup, list-ingredients-overreach) so the fine-tuned model
has to learn the actual distinction instead of keyword-spotting.

Usage:
    python -m finetune.generate_dataset
"""

from __future__ import annotations

import csv
import random
from pathlib import Path

FINETUNE_DIR = Path(__file__).resolve().parent
DATA_DIR = FINETUNE_DIR / "data"
GOLDEN_CSV = FINETUNE_DIR.parent / "evals" / "golden_dataset.csv"

CATEGORIES = ["find_recipe", "scale_recipe", "build_indent", "check_anomaly", "general"]
LABEL2ID = {c: i for i, c in enumerate(CATEGORIES)}

RECIPES = [
    "croissant", "financier", "lemon meringue tart", "sourdough starter",
    "sourdough loaf", "brioche", "pate a choux", "ganache", "pate sucree",
    "tart tatin", "banana tart", "Danish pastry", "opera cake", "babka",
    "viennoiserie dough", "macarons", "puff pastry", "pain au levain",
    "pain au chocolat", "country loaf", "choux pastry", "creme patissiere",
    "cinnamon rolls", "kouign-amann", "eclairs", "palmiers",
]

RECIPE_LISTS = [
    "croissants, financiers, and tarts",
    "the tart tatin and financiers",
    "macarons, eclairs, and palmiers",
    "brioche, babka, and cinnamon rolls",
    "the viennoiserie class",
]

# ── Per-category templates ───────────────────────────────────────────────────

FIND_RECIPE_TEMPLATES = [
    "Show me the {recipe} recipe",
    "What ingredients go into a {recipe}?",
    "How do I make {recipe}?",
    "Give me the {recipe} recipe",
    "Can I get the recipe for {recipe}?",
    "What's in a classic {recipe}?",
    "Do we have a recipe for {recipe}?",
    "Pull up the {recipe} recipe",
    "I need the ingredient list for {recipe}",
    "What goes into making {recipe}?",
    "Where's the recipe card for {recipe}?",
]

SCALE_RECIPE_TEMPLATES = [
    "Scale the {recipe} to {portions} portions",
    "Double the {recipe}",
    "Triple the {recipe} batch",
    "I need this recipe for {n} students",
    "Multiply the {recipe} recipe by {n}",
    "Scale {recipe} to {weight}g",
    "Make {recipe} for {n} people",
    "Adjust the {recipe} recipe for {portions} portions",
    "Quadruple the {recipe}",
    "Halve the {recipe} recipe",
]

BUILD_INDENT_TEMPLATES = [
    "Build an indent sheet for {recipe_list}",
    "Create a shopping list for tomorrow's production day",
    "I need to order ingredients for {recipe}",
    "Consolidate all ingredients for {recipe_list}",
    "Generate a purchase list for {recipe}",
    "Compile all the ingredients needed for {recipe_list}",
    "Put together an ordering sheet for {recipe}",
    "Make a prep list for {recipe} production",
    "I need to order ingredients for next week's {recipe} class",
]

CHECK_ANOMALY_TEMPLATES = [
    "Check the {recipe} recipe for ratio errors",
    "Validate the {recipe} ratios",
    "Flag any anomalies in the {recipe} recipe",
    "Is there a problem with the hydration in the {recipe}?",
    "Review the {recipe} for any wrong ratios",
    "Check if the {recipe} recipe has any anomalies",
    "Can you double check the {recipe} recipe for errors?",
    "Validate the measurements in the {recipe}",
    "Something feels off about the {recipe} recipe, can you check it?",
]

# General: pure baking-science questions (no keyword overlap at all)
GENERAL_PLAIN = [
    "What's the difference between Swiss and Italian meringue?",
    "What causes a soggy bottom in a baked tart shell?",
    "Why do enriched doughs take longer to proof than lean doughs?",
    "What's the purpose of degassing dough during bulk fermentation?",
    "Why does chocolate seize when water is added to it?",
    "What's the difference between Dutch-process and natural cocoa powder?",
    "Why do some pastry doughs need to stay cold while you work with them?",
    "What role does gluten development play in a laminated pastry?",
    "Why does creaming butter and sugar together add air to a batter?",
    "What's the smoke point difference between butter and clarified butter?",
    "What causes macarons to develop feet during baking?",
    "Why do you fold laminated dough instead of just rolling it out flat?",
    "What's the difference between baking soda and baking powder chemically?",
    "Why does egg wash give pastry a shiny golden crust?",
    "What's the purpose of scoring bread dough before it goes in the oven?",
    "Why does whipped cream deflate faster in a warm kitchen?",
    "What's the difference between tempered and untempered chocolate?",
    "Why do some tart shells get blind-baked before filling?",
]

# General: templated baking-science questions tied to a specific recipe, to
# keep the "asking about technique/science, not asking FOR the recipe" signal
# strong even when a recipe name is present (a harder negative than generic
# questions with no recipe name at all)
GENERAL_RECIPE_SCIENCE_TEMPLATES = [
    "Why does {recipe} dough need to rest before it's baked?",
    "What happens chemically if {recipe} dough is overmixed?",
    "Why is temperature control especially important when making {recipe}?",
    "What causes {recipe} to turn out dense instead of light?",
    "Why do bakers rest {recipe} dough in the fridge overnight?",
]

# General: the "hard" cases that mirror documented failure clusters but with
# different phrasing than golden_dataset.csv (keyword bleed -- ratio/correct/
# check/order/yield/technique appear but the question is conceptual, not
# about a specific named recipe or an ordering/scaling action)
GENERAL_KEYWORD_BLEED = [
    "What's a typical ratio of sugar to egg whites in a good meringue?",
    "What's the correct way to laminate butter into dough in general?",
    "How can you tell if caramel has crystallized incorrectly?",
    "What's the right order to add wet and dry ingredients when mixing cake batter?",
    "What does a typical production day look like at a pastry school?",
    "What's the science behind why long fermentation improves sourdough flavor?",
    "How does over-proofing affect the texture of an enriched dough?",
    "Does swapping bread flour for cake flour yield a chewier crumb?",
    "List the top techniques every pastry student should learn first",
    "What's a good hydration ratio for a rustic loaf in general?",
    "Why is checking dough temperature important during mixing?",
    "What's the correct internal temperature to check for a baked custard, generally speaking?",
    "What order should a beginner learn pastry techniques in?",
    "How do you review whether any dough has been kneaded enough?",
    "What technique is responsible for puff pastry's flaky layers?",
    "What's considered the correct hydration percentage for a baguette?",
    "How do you check whether yeast is still active before using it?",
]

# General: double-check idiom (not a scale instruction)
GENERAL_DOUBLE_CHECK = [
    "Can you double check why caramel tends to seize up?",
    "I should double check -- does baking soda expire over time?",
    "Let me double check, is bread flour the same thing as strong flour?",
    "Just want to double check, is Dutch-process cocoa the same as natural cocoa?",
    "Double check for me -- do you need to sift powdered sugar before using it?",
]

# find_recipe: portions/yield phrasing that must NOT be hijacked into scale_recipe
FIND_RECIPE_PORTIONS = [
    "How many portions does the {recipe} recipe make?",
    "Show me a recipe that yields about {portions} portions",
    "How many servings does a batch of {recipe} produce?",
    "What yield should I expect from the {recipe} recipe?",
]

# find_recipe: "list ingredients" simple lookup that must NOT be hijacked into build_indent
FIND_RECIPE_LIST_INGREDIENTS = [
    "List the ingredients in the {recipe} recipe",
    "Can you list what's in the {recipe}?",
    "List out the ingredients for {recipe}",
]

PORTIONS = [10, 12, 20, 24, 30, 40, 50, 60, 75, 100]
WEIGHTS = [250, 400, 500, 700, 1000, 1500, 2000]
MULTIPLIERS = [2, 3, 4, 5]


def _fill(template: str, rng: random.Random) -> str:
    return template.format(
        recipe=rng.choice(RECIPES),
        recipe_list=rng.choice(RECIPE_LISTS),
        n=rng.choice(PORTIONS),
        portions=rng.choice(PORTIONS),
        weight=rng.choice(WEIGHTS),
    )


def generate_rows(seed: int = 42) -> list[dict]:
    rng = random.Random(seed)
    rows: list[dict] = []

    def add(templates: list[str], label: str, per_template: int = 8) -> None:
        for t in templates:
            seen_for_template: set[str] = set()
            attempts = 0
            while len(seen_for_template) < per_template and attempts < per_template * 5:
                attempts += 1
                text = _fill(t, rng)
                if text not in seen_for_template:
                    seen_for_template.add(text)
                    rows.append({"text": text, "label": label})

    add(FIND_RECIPE_TEMPLATES, "find_recipe", per_template=5)
    add(FIND_RECIPE_PORTIONS, "find_recipe", per_template=5)
    add(FIND_RECIPE_LIST_INGREDIENTS, "find_recipe", per_template=5)

    add(SCALE_RECIPE_TEMPLATES, "scale_recipe", per_template=7)

    add(BUILD_INDENT_TEMPLATES, "build_indent", per_template=8)

    add(CHECK_ANOMALY_TEMPLATES, "check_anomaly", per_template=8)

    add(GENERAL_RECIPE_SCIENCE_TEMPLATES, "general", per_template=6)
    for text in GENERAL_PLAIN + GENERAL_KEYWORD_BLEED + GENERAL_DOUBLE_CHECK:
        rows.append({"text": text, "label": "general"})

    return rows


def dedupe_and_remove_leakage(rows: list[dict]) -> list[dict]:
    golden_texts: set[str] = set()
    if GOLDEN_CSV.exists():
        with open(GOLDEN_CSV, newline="", encoding="utf-8") as f:
            golden_texts = {r["query"].strip().lower() for r in csv.DictReader(f)}

    seen: set[str] = set()
    deduped = []
    for r in rows:
        key = r["text"].strip().lower()
        if key in seen or key in golden_texts:
            continue
        seen.add(key)
        deduped.append(r)
    return deduped


def stratified_split(rows: list[dict], val_fraction: float, seed: int) -> tuple[list[dict], list[dict]]:
    """80/20 split per label so each class keeps the same ratio in train/val,
    avoiding sklearn as a dependency for a single split operation."""
    rng = random.Random(seed)
    train, val = [], []
    for c in CATEGORIES:
        group = [r for r in rows if r["label"] == c]
        rng.shuffle(group)
        cut = max(1, round(len(group) * val_fraction))
        val.extend(group[:cut])
        train.extend(group[cut:])
    rng.shuffle(train)
    rng.shuffle(val)
    return train, val


def write_csv(path: Path, rows: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["text", "label"])
        w.writeheader()
        w.writerows(rows)


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    rows = generate_rows()
    rows = dedupe_and_remove_leakage(rows)
    random.Random(42).shuffle(rows)

    train_rows, val_rows = stratified_split(rows, val_fraction=0.2, seed=42)

    write_csv(DATA_DIR / "dataset.csv", rows)
    write_csv(DATA_DIR / "train.csv", train_rows)
    write_csv(DATA_DIR / "val.csv", val_rows)

    print(f"Total rows: {len(rows)} (train {len(train_rows)} / val {len(val_rows)})")
    print("\nPer-category counts (full dataset):")
    for c in CATEGORIES:
        count = sum(1 for r in rows if r["label"] == c)
        print(f"  {c:<15}{count}")
    print(f"\nWrote {DATA_DIR / 'dataset.csv'}")
    print(f"Wrote {DATA_DIR / 'train.csv'}")
    print(f"Wrote {DATA_DIR / 'val.csv'}")


if __name__ == "__main__":
    main()

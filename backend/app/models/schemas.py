from __future__ import annotations
from typing import Any, Optional
from pydantic import BaseModel, Field


class Ingredient(BaseModel):
    name: str
    qty_g: float
    pct: Optional[float] = None


class RecipeComponent(BaseModel):
    component_name: str
    yield_label: str = ""
    ingredients: list[Ingredient] = []
    total_g: float = 0.0
    method: list[str] = []


class RecipeChunk(BaseModel):
    chunk_id: str
    source_file: str
    recipe_name: str
    recipe_number: str = ""
    component_name: str
    yield_label: str = ""
    ingredients: list[Ingredient] = []
    total_g: float = 0.0
    method: list[str] = []
    method_raw: str = ""   # verbatim lines from PDF, no merging or modification
    text: str = ""
    # Section heading this recipe belongs to (e.g. "Berliner Variations").
    # Stored as metadata only — not embedded in chunk text — so it doesn't
    # pollute BM25/semantic search. Used for section-based retrieval expansion.
    parent_section: str = ""
    metadata: dict[str, Any] = {}


# ── Chat API ──────────────────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = []


# ── Tool results (serialised into SSE events) ─────────────────────────────────

class ScaledIngredient(BaseModel):
    name: str
    original_qty_g: float
    scaled_qty_g: float
    non_linear_warning: bool = False


class ScaleResult(BaseModel):
    recipe_name: str
    component_name: str
    original_yield: float
    target_yield: float
    scale_factor: float
    scaled_ingredients: list[ScaledIngredient]
    warnings: list[str] = []


class IndentRow(BaseModel):
    ingredient: str
    category: str
    total_qty_g: float
    sources: list[str]


class IndentSheet(BaseModel):
    recipes: list[str]
    rows: list[IndentRow]


class AnomalyResult(BaseModel):
    ingredient: str
    component: str
    recipe: str
    actual_g: float
    max_g: float
    min_g: float = 0.0
    actual_pct: Optional[float] = None   # set when rule uses ratio check
    max_pct: Optional[float] = None      # set when rule uses ratio check
    passed: bool
    advice: str


class AnomalyReport(BaseModel):
    recipe_name: str
    results: list[AnomalyResult]
    overall_pass: bool


# ── SSE event envelope ────────────────────────────────────────────────────────

class SSEEvent(BaseModel):
    type: str  # "status" | "token" | "result" | "error" | "done"
    content: Any = None

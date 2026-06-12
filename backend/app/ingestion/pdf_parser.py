"""
Parse pastry academy PDF handouts into structured RecipeChunk objects.

Expected page format (from real academy PDFs):

    1. Soft Rolls
    DOUGH
    – per person
    Ingredients Qty (g) %
    Flour 130 100.0%
    Yeast 3 2.3%
    ...
    Total 235.5
    METHOD
    1. Combine flour ...

Every component fits on one page in the academy format.
The parser resets mode flags at each page boundary — this prevents
in_method=True from leaking across pages and silently dropping recipe headings.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Optional

import pdfplumber

from app.models.schemas import Ingredient, RecipeChunk

# ── Patterns ──────────────────────────────────────────────────────────────────

_RE_RECIPE_HEADING = re.compile(r"^\d+\.\s+(.+)$")
_RE_YIELD = re.compile(r"^[–\-]\s*(.+)$")
_RE_TOTAL = re.compile(r"^Total\s+([\d,.]+)", re.IGNORECASE)
_RE_METHOD_STEP = re.compile(r"^\d+\.\s+.+")
_RE_PAGE_NUMBER = re.compile(r"^\|\s*\d+\s*$")

# Lines to discard entirely
_SKIP_TOKENS = {
    "CONTENTS", "C O N T E N T S", "INDENT", "WORKFLOW", "PREP LIST",
    "ASSEMBLY",
    # NOTE: "METHOD:" intentionally NOT here — it is handled by the method-mode
    # detection below and must NOT be discarded before that check runs.
}

# Verb prefixes that flag a numbered line as a method instruction, not a recipe name
_METHOD_VERBS = re.compile(
    r"^(mix|add|bake|heat|preheat|pour|combine|cut|brush|arrange|cook|decrease|roll|fold|"
    r"whisk|melt|cool|chill|rest|proof|fry|boil|simmer|stir|transfer|reserve|place|"
    r"allow|continue|repeat|remove|prepare|knead|shape|pipe|fill|coat|dip|drain|"
    r"flash|use|apply|make|set|let|leave|check|test|for\s|"
    r"warm|whip|season|cream\s|blitz|sheet|smooth|emulsify|temper|dry\s|"
    r"lastly|then\s|keep|glaze|sieve|sift|grate|chop|slice|score|garnish|"
    r"serve|refrigerate|freeze|thaw|sprinkle|dust|press|trim|decorate|infuse|"
    r"strain|pass|weigh|portion|line|grease|spread|flatten|wrap|seal)",
    re.IGNORECASE,
)


def _looks_like_method_step(name: str) -> bool:
    """True when a numbered line is a method instruction rather than a recipe name."""
    if len(name.split()) >= 7:  # 7+ words are almost always instructions
        return True
    if _METHOD_VERBS.match(name):
        return True
    low = name.lower()
    if any(tok in low for tok in [
        "°c", "°f", "ºc", "ºf", "minutes", "until", " then ", "°", "º",
        " aside", " till ", "before use", "as required", " further ", "melted ",
        "and set", "till smooth", "to a smooth",
    ]):
        return True
    return False



def _is_section_divider(line: str) -> bool:
    """Detect spaced-out section headings like 'B A S I C S I N B R E A D'."""
    stripped = line.strip()
    if len(stripped) < 3:
        return False
    chars = stripped.replace(" ", "")
    if not chars.isalpha():
        return False
    spaces = stripped.count(" ")
    return spaces >= len(chars) - 1


def _is_component_header(line: str) -> bool:
    """
    ALL-CAPS line that is not a reserved keyword and not a page number.
    Allows spaces, digits, & and common punctuation (e.g. 'COFFEE & HAZELNUT MOLLEUX').
    """
    stripped = line.strip()
    if not stripped or len(stripped) < 2:
        return False
    if stripped in ("METHOD", "TOTAL", "INDENT", "WORKFLOW", "PUFF"):
        return False
    if _RE_PAGE_NUMBER.match(stripped):
        return False
    if stripped.isdigit():
        return False
    # Must be entirely uppercase (ignoring spaces, digits, &, comma, #, -)
    alpha_chars = re.sub(r"[^a-zA-Z]", "", stripped)
    if len(alpha_chars) < 3:  # "(G)", "X1" etc. are not component headers
        return False
    return alpha_chars == alpha_chars.upper()


_HEADING_STOP_WORDS = {
    "for", "class", "prep", "time", "demo", "add", "bake", "mix", "make",
    "note", "tip", "step", "place", "heat", "cool", "pour", "strain",
}


def _is_unnumbered_recipe_heading(line: str) -> bool:
    """
    Return True for page-top lines like "Doughnut / Berliner" or
    "Berliner Variations" that don't follow the "N. Name" numbered pattern.

    Rejects:
    - Lines ending with a digit (contents page entries: "Doughnut / Berliner 16")
    - Lines containing a colon (labels: "Class Capacity: 18 Students")
    - Lines that start with common non-recipe words ("For", "Class", "Add"…)
    - Very short or very long lines
    - Lines that are ALL CAPS (already caught as component headers)
    - Lines that contain digits anywhere (quantities, page refs)
    """
    stripped = line.strip()
    if not stripped or len(stripped) < 4 or len(stripped) > 60:
        return False
    if ":" in stripped:
        return False
    if any(ch.isdigit() for ch in stripped):
        return False
    first_word = stripped.split()[0].lower().rstrip("/")
    if first_word in _HEADING_STOP_WORDS:
        return False
    alpha_chars = re.sub(r"[^a-zA-Z]", "", stripped)
    if not alpha_chars:
        return False
    # Must be mixed/title case (not ALL CAPS — those are component headers)
    if alpha_chars == alpha_chars.upper():
        return False
    # Must have at least one alphabetic word (not purely punctuation/numbers)
    words = re.findall(r"[a-zA-Z]+", stripped)
    return len(words) >= 1


def _parse_float(s: str) -> Optional[float]:
    try:
        return float(s.replace(",", "").replace("%", "").strip())
    except ValueError:
        return None


def _chunk_id(source_file: str, recipe_name: str, component_name: str) -> str:
    key = f"{source_file}|{recipe_name}|{component_name}"
    return hashlib.sha256(key.encode()).hexdigest()[:32]


def _build_chunk_text(
    recipe_name: str,
    component_name: str,
    yield_label: str,
    ingredients: list[Ingredient],
    total_g: float,
    method: list[str],
) -> str:
    lines = [f"Recipe: {recipe_name}", f"Component: {component_name}"]
    if yield_label:
        lines.append(f"Yield: {yield_label}")
    lines.append("Ingredients:")
    for ing in ingredients:
        pct_str = f"  ({ing.pct:.1f}%)" if ing.pct is not None else ""
        lines.append(f"  {ing.name}: {ing.qty_g}g{pct_str}")
    if total_g:
        lines.append(f"Total: {total_g}g")
    if method:
        lines.append("Method:")
        lines.extend(method)
    return "\n".join(lines)


# ── State machine ─────────────────────────────────────────────────────────────

class _ParserState:
    def __init__(self, source_file: str):
        self.source_file = source_file
        self.chunks: list[RecipeChunk] = []

        self.current_recipe_name = ""
        self.current_recipe_number = ""
        self.current_component = ""
        self.current_yield = ""
        self.current_ingredients: list[Ingredient] = []
        self.current_total = 0.0
        self.current_method: list[str] = []

        # Tracks section headings like "Berliner Variations" or "Doughnuts Variations".
        # Persists until overwritten by the next unnumbered heading.
        # Included in chunk text so sub-recipes are searchable by section name.
        self.current_section_heading = ""

        self.in_ingredients = False
        self.in_method = False
        self.at_page_start = False  # True for the first meaningful line of each page
        self.current_method_raw: list[str] = []  # verbatim lines, no merging

    def reset_page(self) -> None:
        """
        Called at each page boundary.
        Resets ingredient mode (tables never span pages in this format).
        Does NOT reset in_method — method sections frequently overflow a page
        (e.g. Croissant Dough steps 14-15 on the page after the ingredient table).
        New recipe/component headers encountered while in_method=True will
        exit method mode explicitly via _start_recipe / _start_component.
        Does NOT clear current_section_heading — sections span multiple pages.
        """
        self.in_ingredients = False
        self.at_page_start = True

    def _flush_component(self) -> None:
        if not self.current_component or not self.current_ingredients:
            return
        text = _build_chunk_text(
            self.current_recipe_name,
            self.current_component,
            self.current_yield,
            self.current_ingredients,
            self.current_total,
            self.current_method,
        )
        self.chunks.append(RecipeChunk(
            chunk_id=_chunk_id(
                self.source_file,
                self.current_recipe_name,
                self.current_component,
            ),
            source_file=self.source_file,
            recipe_name=self.current_recipe_name,
            recipe_number=self.current_recipe_number,
            component_name=self.current_component,
            yield_label=self.current_yield,
            ingredients=list(self.current_ingredients),
            total_g=self.current_total,
            method=list(self.current_method),
            method_raw="\n".join(self.current_method_raw),
            text=text,
            parent_section=self.current_section_heading,
        ))

    def _start_component(self, name: str) -> None:
        self._flush_component()
        self.current_component = name
        self.current_yield = ""
        self.current_ingredients = []
        self.current_total = 0.0
        self.current_method = []
        self.current_method_raw = []
        self.in_ingredients = False
        self.in_method = False

    def _start_recipe(self, name: str, number: str) -> None:
        self._flush_component()
        self.current_recipe_name = name
        self.current_recipe_number = number
        self.current_component = ""
        self.current_yield = ""
        self.current_ingredients = []
        self.current_total = 0.0
        self.current_method = []
        self.current_method_raw = []
        self.in_ingredients = False
        self.in_method = False

    def process_line(self, line: str) -> None:
        stripped = line.strip()
        if not stripped:
            return
        if _RE_PAGE_NUMBER.match(stripped):
            return
        if _is_section_divider(stripped):
            return
        if stripped.upper() in _SKIP_TOKENS:
            # "Indent" and "Workflow" mark the end of a recipe section in this
            # booklet format. Clear the section heading so recipes in the next
            # class don't inherit a stale section tag.
            if stripped.upper() in ("INDENT", "WORKFLOW", "PREP LIST"):
                self.current_section_heading = ""
            return

        low = stripped.lower()

        # ── Table header → enter ingredients mode ─────────────────────────
        if "ingredients" in low and ("qty" in low or "quantity" in low):
            self.at_page_start = False
            self.in_ingredients = True
            self.in_method = False
            # Recipe has no ALL-CAPS component header (e.g. "Doughnut / Berliner").
            # Use the recipe name as the component so _flush_component fires.
            if not self.current_component and self.current_recipe_name:
                self.current_component = self.current_recipe_name
            return

        # ── METHOD keyword ────────────────────────────────────────────────
        if re.match(r"^METHOD\s*:?\s*$", stripped, re.IGNORECASE):
            self.at_page_start = False
            self.in_ingredients = False
            self.in_method = True
            return

        # ── Component header (ALL CAPS) → always starts a new component ──
        if _is_component_header(stripped):
            self.at_page_start = False
            self._start_component(stripped.title())
            return

        # ── Recipe heading: numbered "N. Name" ────────────────────────────
        # Checked even when in_method=True so that cross-page method sections
        # don't swallow the first line of the next recipe (e.g. Croissant Dough
        # steps 14-15 on page 189, followed by "2. Pain Au Chocolat").
        if not self.in_ingredients:
            m = _RE_RECIPE_HEADING.match(stripped)
            if m:
                name = m.group(1).strip()
                if not _looks_like_method_step(name):
                    self.at_page_start = False
                    self.in_method = False   # explicit exit from any active method section
                    self._start_recipe(
                        name=name,
                        number=stripped.split(".")[0].strip(),
                    )
                    return

        # ── Recipe heading: unnumbered — first meaningful line of a new page ──
        if self.at_page_start and not self.in_ingredients:
            if _is_unnumbered_recipe_heading(stripped):
                self.at_page_start = False
                self.in_method = False   # explicit exit
                self._start_recipe(name=stripped, number="")
                self.current_section_heading = stripped
                return

        self.at_page_start = False

        # ── Total row ─────────────────────────────────────────────────────
        m = _RE_TOTAL.match(stripped)
        if m:
            val = _parse_float(m.group(1))
            if val is not None:
                self.current_total = val
            self.in_ingredients = False
            return

        # ── Yield label ───────────────────────────────────────────────────
        if not self.in_method and not self.in_ingredients:
            m = _RE_YIELD.match(stripped)
            if m:
                self.current_yield = m.group(1).strip()
                return

        # ── Method content (numbered step, sub-label, or continuation) ──
        if self.in_method:
            # Raw: preserve every line exactly as it appears in the PDF
            self.current_method_raw.append(stripped)

            # Parsed list: merge wrapped continuation lines for tool use
            if _RE_METHOD_STEP.match(stripped):
                self.current_method.append(stripped)
            elif self.current_method and stripped[0:1].islower():
                # Continuation of previous step — merge (e.g. "hot oil." wrapping)
                self.current_method[-1] = self.current_method[-1] + " " + stripped
            else:
                # Sub-section label like "For Doughnuts:" or "For Frying:"
                self.current_method.append(stripped)
            return

        # ── Ingredient row ────────────────────────────────────────────────
        if self.in_ingredients and self.current_component:
            self._parse_ingredient_line(stripped)

    def _parse_ingredient_line(self, stripped: str) -> None:
        """
        Parse ingredient rows. Handles three table formats:
          - "Name qty pct%"           (standard 3-column)
          - "Name qty"                (2-column, no pct)
          - "Name X1_qty X2_qty pct%" (multi-column: e.g. "X1 Qty, X1/2 Qty, %")
        Uses rsplit from the right so multi-word ingredient names are preserved.
        For multi-column tables, the first (X1 / full batch) quantity is used.
        """
        # Multi-column check: 4 tokens where the middle two are both numeric
        parts4 = stripped.rsplit(None, 3)
        if len(parts4) == 4:
            qty_val = _parse_float(parts4[1])
            qty_val2 = _parse_float(parts4[2])
            if qty_val is not None and qty_val2 is not None:
                pct_val = _parse_float(parts4[3])
                self.current_ingredients.append(
                    Ingredient(name=parts4[0], qty_g=qty_val, pct=pct_val)
                )
                return

        parts = stripped.rsplit(None, 2)
        if len(parts) < 2:
            return

        if len(parts) == 3:
            qty_val = _parse_float(parts[1])
            pct_val = _parse_float(parts[2])
            if qty_val is not None:
                self.current_ingredients.append(
                    Ingredient(name=parts[0], qty_g=qty_val, pct=pct_val)
                )
                return
            # Fallback: last token is qty, no pct
            qty_val2 = _parse_float(parts[2])
            if qty_val2 is not None:
                ing_name = f"{parts[0]} {parts[1]}"
                self.current_ingredients.append(
                    Ingredient(name=ing_name, qty_g=qty_val2)
                )
            return

        if len(parts) == 2:
            qty_val = _parse_float(parts[1])
            if qty_val is not None:
                self.current_ingredients.append(
                    Ingredient(name=parts[0], qty_g=qty_val)
                )

    def finalise(self) -> list[RecipeChunk]:
        self._flush_component()
        return self.chunks


# ── Page-level fallback chunking ──────────────────────────────────────────────

def _page_chunk_id(source_file: str, page_num: int) -> str:
    key = f"{source_file}|page|{page_num}"
    return hashlib.sha256(key.encode()).hexdigest()[:32]


def _fallback_page_chunks(pdf_path: Path) -> list[RecipeChunk]:
    """
    Chunk the PDF page-by-page for non-academy-format PDFs (notes, articles).
    Each page becomes one searchable chunk.
    """
    chunks = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text()
            if not text or len(text.strip()) < 50:
                continue
            chunks.append(RecipeChunk(
                chunk_id=_page_chunk_id(pdf_path.name, i),
                source_file=pdf_path.name,
                recipe_name="",
                recipe_number="",
                component_name=f"Page {i + 1}",
                yield_label="",
                ingredients=[],
                total_g=0.0,
                method=[],
                text=text.strip(),
                metadata={"chunk_type": "knowledge"},
            ))
    return chunks


# ── Public API ────────────────────────────────────────────────────────────────

def parse_pdf(pdf_path: str | Path) -> list[RecipeChunk]:
    """
    Parse a pastry academy PDF into RecipeChunk objects (one per component).

    Strategy:
      1. Structured parser: extracts ingredient tables and methods.
         Mode flags are reset at each page boundary.
      2. If < 3 structured components found, fall back to page-level chunking
         so non-academy PDFs (notes, articles) are still fully searchable.
    """
    pdf_path = Path(pdf_path)
    state = _ParserState(source_file=pdf_path.name)

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue
            state.reset_page()          # ← key: reset mode at every page boundary
            for line in text.split("\n"):
                state.process_line(line)

    structured = state.finalise()

    if len(structured) >= 3:
        return structured

    return structured + _fallback_page_chunks(pdf_path)

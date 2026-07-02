"""
LangGraph agent for Pâtisserie AI.

Graph nodes:
  classify_intent → route → [recipe_finder | scaler | indent_builder |
                              anomaly_checker | general_knowledge] → format_response → END

The LLM only runs at:
  - Intent classification (fast, cheap, deterministic prompt)
  - HyDE inside hybrid_retriever (only for ambiguous queries)
  - format_response (stream tokens to the client)

All arithmetic is in the deterministic tool functions.
"""

from __future__ import annotations

import json
import re
from typing import Any, AsyncIterator, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph

from app.agent.prompts import (
    FORMAT_ANOMALY_PROMPT,
    FORMAT_GENERAL_PROMPT,
    FORMAT_INDENT_PROMPT,
    FORMAT_RECIPE_PROMPT,
    FORMAT_SCALE_PROMPT,
    INTENT_SYSTEM,
    LOW_CONFIDENCE_PROMPT,
    SYSTEM_PROMPT,
)
from app.config import settings
from app.tools.anomaly_checker import check_anomalies
from app.tools.indent_sheet import build_indent_sheet
from app.tools.recipe_finder import find_recipes
from app.tools.scaler import scale_recipe


# ── LLM ──────────────────────────────────────────────────────────────────────

def _llm(streaming: bool = False) -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.nebius_llm_model,
        api_key=settings.nebius_api_key,
        base_url=settings.nebius_base_url,
        temperature=0.1,
        streaming=streaming,
    )


def _intent_llm() -> ChatOpenAI:
    """Separate from _llm() so the classifier's model can be swapped
    (e.g. to a fine-tuned classifier) without affecting response generation."""
    return ChatOpenAI(
        model=settings.nebius_intent_model,
        api_key=settings.nebius_api_key,
        base_url=settings.nebius_base_url,
        temperature=0.1,
        streaming=False,
    )


# ── State ─────────────────────────────────────────────────────────────────────

class AgentState(TypedDict):
    query: str
    history: list[dict]
    intent: str
    tool_output: Any
    confidence: float
    status_steps: list[str]
    final_prompt: str
    direct_response: str  # if set, skip LLM and emit this text directly


# ── Intent classification ─────────────────────────────────────────────────────

_INTENT_KEYWORDS = {
    "scale_recipe": [
        "scale", "double", "triple", "quadruple", "half", "portion",
        "portions", "people", "students", "yield", "multiply",
    ],
    "build_indent": [
        "indent", "order", "ordering", "prep list", "production day",
        "consolidat", "shopping list", "purchase", "all ingredients",
    ],
    "check_anomaly": [
        "check", "anomal", "ratio", "valid", "error", "wrong",
        "correct", "issue", "problem", "flag", "review",
    ],
    "find_recipe": [
        "recipe", "find", "show", "give", "how to make", "ingredient",
        "what is", "how do", "technique", "method",
    ],
}

# Keywords that are prone to bleeding into general baking-science questions
# ("what's the correct ratio...", "how does X affect Y") rather than the
# action they normally signal. Only trusted when the query ISN'T phrased as
# an informational question (see _is_general_question below).
_WEAK_KEYWORDS = {
    "check_anomaly": {"ratio", "correct", "check", "review"},
    "build_indent": {"order", "production day"},
    "find_recipe": {"recipe", "technique", "how do"},
    "scale_recipe": {"yield"},
}

_QUESTION_START = re.compile(r"^(what|why|how|does|is|are|can|could|would)\b")


def _is_general_question(low: str) -> bool:
    return bool(_QUESTION_START.match(low.strip()))


def _classify_intent(query: str) -> str:
    low = query.lower()

    # Weight quantity + recipe context → user wants a scaled recipe
    # e.g. "give me Banana Tart recipe for 700gms"
    if re.search(r'\b\d[\d,.]*\s*(?:gms?|g(?:rams?)?|kg)\b', low):
        if any(kw in low for kw in ("recipe", "make", "give", "show", "find")):
            if not any(kw in low for kw in _INTENT_KEYWORDS["check_anomaly"]):
                return "scale_recipe"

    # "compile ingredients for X" / "list ALL ingredients for X" → consolidated
    # ingredient list = build_indent. Requires "compile", or "list" together with
    # "all", so a simple recipe lookup ("list the ingredients in X recipe") falls
    # through to find_recipe instead of being treated as an indent-sheet request.
    if re.search(r'\bcompile\b.{0,60}\bingredients?\b', low):
        return "build_indent"
    if re.search(r'\blist\b.{0,60}\ball\b.{0,60}\bingredients?\b', low):
        return "build_indent"

    # "double check"/"double-check" is an idiom about verification, not a
    # scaling instruction -- don't let the literal word "double" claim it.
    is_double_check_idiom = bool(re.search(r"\bdouble[\s-]?check", low))

    # Fast keyword pre-check before LLM call. Weak/ambiguous keywords are
    # skipped on general-question phrasing so they don't hijack baking-science
    # questions -- those queries fall through to the LLM fallback instead.
    is_question = _is_general_question(low)
    for intent, keywords in _INTENT_KEYWORDS.items():
        weak = _WEAK_KEYWORDS.get(intent, set())
        for kw in keywords:
            if kw == "double" and is_double_check_idiom:
                continue
            if kw in low and not (kw in weak and is_question):
                return intent

    # LLM fallback for ambiguous queries
    llm = _intent_llm()
    resp = llm.invoke([
        SystemMessage(content=INTENT_SYSTEM),
        HumanMessage(content=query),
    ])
    label = resp.content.strip().lower()
    valid = {"find_recipe", "scale_recipe", "build_indent", "check_anomaly", "general"}
    return label if label in valid else "general"


# ── Parameter extraction helpers ─────────────────────────────────────────────

def _extract_recipe_name(query: str) -> str:
    """Heuristic: remove scaling/check verbs and weight quantities, return the recipe noun phrase."""
    # Quoted strings: if the query has two quoted strings in "X in Y" pattern,
    # Y is the recipe; if only one, that is the recipe.
    quotes = re.findall(r"['\"](.+?)['\"]", query)
    if quotes:
        m = re.search(r"['\"].+?['\"].*?\bin\b.*?['\"](.+?)['\"]", query, re.IGNORECASE)
        if m:
            return m.group(1).strip()
        return quotes[-1].strip()

    # Strip weight quantities first so patterns don't trip on them
    q = re.sub(r'\b\d[\d,.]*\s*(?:gms?|g(?:rams?)?|kg(?:ilograms?)?)\b', '', query, flags=re.IGNORECASE).strip()
    q = re.sub(r'\s{2,}', ' ', q)

    for pattern in [
        # "to make / make <name> of/to/for" — catches "to make Banana Tart of 700gms"
        r"(?:to\s+make|make)\s+(?:the\s+)?(.+?)\s+(?:of|to|for)\s",
        # "to make <name> give/recipe/and" — trailing filler
        r"(?:to\s+make|make)\s+(?:the\s+)?(.+?)\s+(?:give|recipe|and)\b",
        r"scale\s+(?:the\s+)?(.+?)\s+(?:to|for|by)",
        r"check\s+(?:the\s+)?(.+?)\s+(?:for|recipe)?",
        r"(?:find|show me|show|give me)\s+(?:the\s+)?(.+?)(?:\s+recipe)?$",
        # "For Banana Tart can you list / compile / tell me..." — recipe is before the verb
        r"^(?:for|regarding)\s+(?:the\s+|a\s+)?(.+?)\s+(?:can\s+you|could\s+you|please|tell\s+me|list|compile|show|give|provide|what)\b",
        # "for a/the <component>[?] in <recipe>" — recipe is after "in"
        r"\bfor\s+(?:a\s+|the\s+)?(?:.+?)[\s?]+\bin\b\s+(.+?)(?:\?|$)",
    ]:
        m = re.search(pattern, q, re.IGNORECASE)
        if m:
            name = m.group(1).strip()
            # Remove any lingering trailing filler words
            name = re.sub(r'\s+(?:recipe|and|qty|quantity|of|for)[\s,]*$', '', name, flags=re.IGNORECASE).strip()
            if len(name) > 3:
                return name
    return q.strip() or query.strip()


_GENERIC_RECIPE_NAMES = {
    "recipe", "the recipe", "a recipe", "it", "this", "that",
    "this recipe", "that recipe", "the dish", "dish",
}


def _is_generic_recipe_name(name: str) -> bool:
    return not name or name.lower().strip() in _GENERIC_RECIPE_NAMES or len(name.strip()) <= 2


def _extract_component_name(query: str) -> str | None:
    """
    Try to extract a component name when the user wants to scale only one
    component inside a multi-component recipe.

    Handles:
      'banana cake' in 'Banana Tart'              → "banana cake"
      for a banana cake? in Banana Tart           → "banana cake"
      for a banana cake in Banana Tart            → "banana cake"
      only the banana cake component              → "banana cake"
      qty of banana cake                          → "banana cake"
      divide/halve banana cake by half            → "banana cake"
    """
    # 1. "quoted_component" in ... (quoted or unquoted recipe follows)
    m = re.search(r"['\"](.+?)['\"][\s?]*\bin\b", query, re.IGNORECASE)
    if m:
        candidate = m.group(1).strip()
        if not _is_generic_recipe_name(candidate):
            return candidate

    # 2. "for a/the <component>[?] in <recipe>" — unquoted component before "in"
    m = re.search(
        r"\bfor\s+(?:a\s+|the\s+)?(.+?)[\s?]+\bin\b",
        query,
        re.IGNORECASE,
    )
    if m:
        candidate = m.group(1).strip().rstrip('?').strip()
        if candidate and not _is_generic_recipe_name(candidate) and len(candidate) < 50:
            return candidate

    # 3. "only (the)? <name> (component)?"
    m = re.search(
        r"\bonly\b.*?(?:the\s+)?(.+?)(?:\s+component)?\s*(?:in\s+|of\s+|\?|$)",
        query,
        re.IGNORECASE,
    )
    if m:
        candidate = m.group(1).strip()
        if candidate and not _is_generic_recipe_name(candidate) and len(candidate) < 40:
            return candidate

    # 4. "qty/quantity of <component>"
    m = re.search(r"(?:qty|quantity)\s+of\s+(.+?)(?:\?|$)", query, re.IGNORECASE)
    if m:
        candidate = m.group(1).strip()
        if candidate and not _is_generic_recipe_name(candidate):
            return candidate

    return None


def _extract_scale_params(query: str) -> dict:
    """
    Parse a scaling query into a dict of kwargs for scale_recipe().

    Handles:
      "to 2000g" / "to 2kg"                       → {target_yield: 2000}
      "4 portions of 50g each"                    → {portions: 4, portion_size_g: 50}
      "for 20 students/people"                    → {portions: 20}
      "double" / "triple"                         → {multiplier: 2 / 3}
      "multiply by 5" / "x3"                      → {multiplier: N}
      "'comp' in 'recipe' by half"                → {component_name: "comp", multiplier: 0.5}
    """
    low = query.lower()
    recipe_name = _extract_recipe_name(query)
    component_name = _extract_component_name(query)

    base = {"recipe_name": recipe_name}
    if component_name:
        base["component_name"] = component_name

    # 1. "X portions of Yg each" / "X pieces at Yg"
    m = re.search(
        r"(\d+)\s*(?:portions?|pieces?|cookies?|items?|pcs?)\s+(?:of|at|@)\s*(\d+(?:\.\d+)?)\s*g",
        low,
    )
    if m:
        return {**base, "portions": int(m.group(1)), "portion_size_g": float(m.group(2))}

    # 2. Multiplier words
    word_mult = {"double": 2.0, "triple": 3.0, "quadruple": 4.0, "half": 0.5}
    for word, factor in word_mult.items():
        if word in low:
            return {**base, "multiplier": factor}

    # 3. "multiply by N" / "x3" / "3x" / "×4"
    m = re.search(r"(?:multiply\s+by|x|×)\s*(\d+(?:\.\d+)?)|(\d+(?:\.\d+)?)\s*(?:x|×)", low)
    if m:
        factor = float(m.group(1) or m.group(2))
        return {**base, "multiplier": factor}

    # 4. "for N people/students/portions" (no size given) → portions only
    m = re.search(
        r"(?:for|yield|to)\s+(\d+)\s*(?:people|students?|persons?|pax|portions?|serves?)",
        low,
    )
    if m:
        return {**base, "portions": int(m.group(1))}

    # 5. Weight target: "to 2000g" / "to 2kg" / "700gms"
    m = re.search(r"(\d[\d,]*)\s*(?:gms?|g(?:rams?)?|kg(?:ilograms?)?)\b", low)
    if m:
        val = float(m.group(1).replace(",", ""))
        target = val * 1000 if "kg" in m.group(0) else val
        return {**base, "target_yield": target}

    # 6. Bare number (assume grams)
    m = re.search(r"\b(\d{3,})\b", query)
    if m:
        return {**base, "target_yield": float(m.group(1))}

    return {**base, "target_yield": 0.0}


def _extract_indent_params(query: str) -> list[dict]:
    """
    Extract list of {recipe_name, target_yield_g} from an indent query.
    Supports comma-separated recipe names.
    """
    # "For X / compile ingredients for X" — use recipe name extractor directly
    if re.search(r'\b(?:compile|list)\b.{0,60}\bingredients?\b', query, re.IGNORECASE):
        name = _extract_recipe_name(query)
        if name and not _is_generic_recipe_name(name):
            return [{"recipe_name": name, "target_yield_g": None}]

    # Remove common preamble
    clean = re.sub(
        r"(build|create|make|generate|indent|prep list|ordering sheet|for)\s+",
        "",
        query,
        flags=re.IGNORECASE,
    ).strip()

    # Split on commas or "and"
    parts = re.split(r",\s*|\s+and\s+", clean, flags=re.IGNORECASE)
    targets = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        # Check for yield: "Croissant x12" or "Croissant (500g)"
        m = re.search(r"(?:x|×)\s*(\d+)|(?:\((\d+)\s*(?:g|kg)?\))", part, re.IGNORECASE)
        yield_g = 0.0
        if m:
            val = float(m.group(1) or m.group(2))
            yield_g = val
            part = re.sub(r"(?:x|×)\s*\d+|\(\d+[^)]*\)", "", part).strip()
        targets.append({"recipe_name": part, "target_yield_g": yield_g or None})
    return targets if targets else [{"recipe_name": clean, "target_yield_g": None}]


# ── Graph nodes ───────────────────────────────────────────────────────────────

def node_classify(state: AgentState) -> AgentState:
    intent = _classify_intent(state["query"])
    state["intent"] = intent
    state["status_steps"] = [f"Intent: {intent.replace('_', ' ')}"]
    return state


def _render_recipes_direct(result: dict) -> str:
    """
    Render matched recipes as exact markdown from stored chunks — no LLM pass.
    Quantities, ingredients, and method steps are copied verbatim; nothing is inferred.
    """
    from collections import defaultdict
    chunks = result.get("chunks", [])
    matched: list[str] = result.get("matched_recipes", [])

    by_recipe: dict[str, list] = defaultdict(list)
    for c in chunks:
        by_recipe[c.recipe_name].append(c)

    blocks: list[str] = []
    for recipe_name in matched:
        recipe_chunks = by_recipe.get(recipe_name, [])
        if not recipe_chunks:
            continue
        source = recipe_chunks[0].source_file
        lines = [f"## {recipe_name}", f"*Source: {source}*", ""]

        for chunk in recipe_chunks:
            lines.append(f"### {chunk.component_name}")
            if chunk.yield_label:
                lines.append(f"*{chunk.yield_label}*")
            lines.append("")
            if chunk.ingredients:
                lines.append("| Ingredient | Qty (g) | % |")
                lines.append("|---|---:|---:|")
                for ing in chunk.ingredients:
                    pct = f"{ing.pct:.1f}" if ing.pct is not None else "—"
                    lines.append(f"| {ing.name} | {ing.qty_g} | {pct} |")
                if chunk.total_g:
                    lines.append(f"| **Total** | **{chunk.total_g}** | |")
            if chunk.method:
                lines.append("")
                lines.append("**Method**")
                for step in chunk.method:
                    lines.append(step)
            lines.append("")

        blocks.append("\n".join(lines))

    return "\n---\n\n".join(blocks)


def node_find_recipe(state: AgentState) -> AgentState:
    state["status_steps"].append("Searching knowledge base...")
    query = state["query"]

    # If the query names a specific recipe (especially with quotes), restrict
    # results to only that recipe so semantically-similar ones don't appear.
    extracted = _extract_recipe_name(query)
    restrict = extracted if (extracted and not _is_generic_recipe_name(extracted) and extracted.lower() != query.lower()) else None

    result = find_recipes(query, restrict_to_name=restrict)
    state["tool_output"] = result
    state["confidence"] = result.get("confidence", 0.0)

    if result.get("low_confidence"):
        state["direct_response"] = (
            "This recipe is not in the uploaded curriculum.\n\n"
            "Upload the relevant PDF via **Upload Recipe Books** to add it to the knowledge base."
        )
        state["confidence"] = 0.0
    # else: recipes are serialised as a structured result — no LLM, no markdown
    return state


def node_scale_recipe(state: AgentState) -> AgentState:
    state["status_steps"].append("Scaling recipe...")
    params = _extract_scale_params(state["query"])
    recipe_name = params.pop("recipe_name")

    # Guard: user didn't name a recipe
    if _is_generic_recipe_name(recipe_name):
        state["direct_response"] = (
            "Please specify the recipe you'd like to scale. For example:\n"
            "- *Scale Croissant Dough to 2000g*\n"
            "- *Double the Berliner Doughnut*\n"
            "- *Scale Banana Caramel & Hazelnut Tart for 30 students*"
        )
        state["tool_output"] = {"error": True}
        state["confidence"] = 1.0
        return state

    has_target = (
        params.get("target_yield", 0) > 0
        or params.get("portions") is not None
        or params.get("multiplier") is not None
    )
    if not has_target:
        state["direct_response"] = (
            f"I need a target yield to scale **{recipe_name}**. Try:\n"
            f"- *Scale {recipe_name} to 2000g*\n"
            f"- *Scale {recipe_name} for 30 students*\n"
            f"- *Double the {recipe_name}*"
        )
        state["tool_output"] = {"error": True}
        state["confidence"] = 1.0
        return state

    result = scale_recipe(recipe_name, **params)
    state["tool_output"] = result
    state["confidence"] = 0.9 if not result.get("error") else 0.3

    if result.get("error"):
        # Use direct_response so errors never go through the LLM
        state["direct_response"] = result.get("message", "Scaling failed.")
    return state


def node_build_indent(state: AgentState) -> AgentState:
    state["status_steps"].append("Consolidating ingredients...")
    targets = _extract_indent_params(state["query"])
    result = build_indent_sheet(targets)
    state["tool_output"] = result
    state["confidence"] = 0.9 if not result.get("error") else 0.3

    if result.get("error"):
        state["final_prompt"] = result.get("message", "Indent sheet build failed.")
    else:
        sheet = result["indent_sheet"]
        state["final_prompt"] = FORMAT_INDENT_PROMPT.format(
            indent_data=json.dumps(sheet.model_dump(), indent=2)
        )
    return state


def node_check_anomaly(state: AgentState) -> AgentState:
    state["status_steps"].append("Checking ratios against thresholds...")
    recipe_name = _extract_recipe_name(state["query"])
    result = check_anomalies(recipe_name)
    state["tool_output"] = result
    state["confidence"] = 0.95 if not result.get("error") else 0.2

    if result.get("error"):
        state["final_prompt"] = result.get("message", "Anomaly check failed.")
    else:
        report = result["anomaly_report"]
        state["final_prompt"] = FORMAT_ANOMALY_PROMPT.format(
            anomaly_data=json.dumps(report.model_dump(), indent=2)
        )
    return state


def node_general(state: AgentState) -> AgentState:
    state["status_steps"].append("Searching knowledge base...")
    from app.retrieval.knowledge_retriever import search_knowledge
    knowledge_chunks = search_knowledge(state["query"], top_k=5)

    # Fall back to structured chunks if semantic index is empty
    if not knowledge_chunks:
        result = find_recipes(state["query"])
        context = "\n\n".join(c.text for c in result.get("chunks", [])[:3])
        state["confidence"] = result.get("confidence", 0.3)
        state["tool_output"] = result
    else:
        context = "\n\n---\n\n".join(
            f"[{c['source_file']} p.{c['page']}]\n{c['text']}"
            for c in knowledge_chunks[:4]
        )
        state["confidence"] = float(knowledge_chunks[0]["score"])
        state["tool_output"] = {"chunks": [], "knowledge_chunks": knowledge_chunks}

    state["final_prompt"] = FORMAT_GENERAL_PROMPT.format(
        query=state["query"],
        context=context or "No relevant context found.",
    )
    return state


def route(state: AgentState) -> str:
    return {
        "find_recipe": "find_recipe",
        "scale_recipe": "scale_recipe",
        "build_indent": "build_indent",
        "check_anomaly": "check_anomaly",
        "general": "general",
    }.get(state["intent"], "general")


# ── Graph assembly ────────────────────────────────────────────────────────────

def build_graph():
    g = StateGraph(AgentState)

    g.add_node("classify", node_classify)
    g.add_node("find_recipe", node_find_recipe)
    g.add_node("scale_recipe", node_scale_recipe)
    g.add_node("build_indent", node_build_indent)
    g.add_node("check_anomaly", node_check_anomaly)
    g.add_node("general", node_general)

    g.set_entry_point("classify")
    g.add_conditional_edges("classify", route)

    for node in ("find_recipe", "scale_recipe", "build_indent", "check_anomaly", "general"):
        g.add_edge(node, END)

    return g.compile()


_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


# ── Streaming entry point ─────────────────────────────────────────────────────

async def run_agent_stream(
    query: str,
    history: list[dict],
) -> AsyncIterator[dict]:
    """
    Progressive streaming — emits status events between each step so the UI
    shows activity immediately rather than waiting for the full pipeline.

    Event types:
      {"type": "status", "content": "..."}   — progress label
      {"type": "result", "content": {...}}   — structured tool data
      {"type": "token",  "content": "..."}   — LLM streaming tokens
      {"type": "meta",   "content": {...}}   — confidence + sources
      {"type": "done"}
    """
    import asyncio

    loop = asyncio.get_event_loop()

    # ── 1. Classify intent (keyword-first, LLM fallback) ─────────────────────
    yield {"type": "status", "content": "Classifying…"}
    intent = await loop.run_in_executor(None, _classify_intent, query)
    yield {"type": "status", "content": f"Intent: {intent.replace('_', ' ')}"}

    state: AgentState = {
        "query": query,
        "history": history,
        "intent": intent,
        "tool_output": None,
        "confidence": 0.5,
        "status_steps": [],
        "final_prompt": "",
        "direct_response": "",
    }

    # ── 2. Run the appropriate tool node ─────────────────────────────────────
    _node_status = {
        "find_recipe":   "Searching knowledge base…",
        "scale_recipe":  "Scaling recipe…",
        "build_indent":  "Consolidating ingredients…",
        "check_anomaly": "Checking ratios…",
        "general":       "Searching knowledge base…",
        # keys match STEP_LABELS in StatusSteps.tsx
    }
    yield {"type": "status", "content": _node_status.get(intent, "Working…")}

    _node_fn = {
        "find_recipe":   node_find_recipe,
        "scale_recipe":  node_scale_recipe,
        "build_indent":  node_build_indent,
        "check_anomaly": node_check_anomaly,
        "general":       node_general,
    }
    node_fn = _node_fn.get(intent, node_general)
    state = await loop.run_in_executor(None, node_fn, state)

    # ── 3. Emit structured result ─────────────────────────────────────────────
    tool_output = state.get("tool_output")
    if tool_output and not tool_output.get("error"):
        yield {"type": "result", "content": _serialise_tool_output(state)}

    # ── 4. Generate response ──────────────────────────────────────────────────
    direct = state.get("direct_response", "")
    if direct:
        # Not-found / error case: emit text directly, no LLM call
        yield {"type": "token", "content": direct}
    elif intent == "find_recipe":
        # Recipes are shown as structured cards — no LLM text needed
        pass
    elif intent in ("scale_recipe", "build_indent") and not (state.get("tool_output") or {}).get("error"):
        # Structured result already rendered — no LLM summary needed
        pass
    else:
        prompt = state.get("final_prompt") or query
        llm = _llm(streaming=True)
        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            *[
                HumanMessage(content=m["content"]) if m["role"] == "user"
                else SystemMessage(content=m["content"])
                for m in history[-6:]
            ],
            HumanMessage(content=prompt),
        ]
        async for chunk in llm.astream(messages):
            if chunk.content:
                yield {"type": "token", "content": chunk.content}

    # ── 5. Metadata + done ────────────────────────────────────────────────────
    yield {
        "type": "meta",
        "content": {
            "confidence": round(state.get("confidence", 0.0), 3),
            "intent": intent,
            "sources": _extract_sources(state),
        },
    }
    yield {"type": "done"}


def _serialise_tool_output(state: AgentState) -> dict:
    from collections import defaultdict
    output = state["tool_output"]
    intent = state["intent"]

    if intent == "find_recipe" and not output.get("low_confidence"):
        chunks = output.get("chunks", [])
        matched: list[str] = output.get("matched_recipes", [])
        by_recipe: dict = defaultdict(list)
        for c in chunks:
            by_recipe[c.recipe_name].append(c)

        recipes_out = []
        for name in matched:
            recipe_chunks = by_recipe.get(name, [])
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
                "components": components,
            })

        return {"type": "recipe_results", "data": {"recipes": recipes_out}}

    if intent == "check_anomaly" and output.get("anomaly_report"):
        return {
            "type": "anomaly_report",
            "data": output["anomaly_report"].model_dump(),
        }
    if intent == "build_indent" and output.get("indent_sheet"):
        return {
            "type": "indent_sheet",
            "data": output["indent_sheet"].model_dump(),
        }
    if intent == "scale_recipe" and output.get("scale_results"):
        return {
            "type": "scale_results",
            "data": [r.model_dump() for r in output["scale_results"]],
        }
    return {}


def _extract_sources(state: AgentState) -> list[dict]:
    output = state.get("tool_output") or {}
    sources: list[dict] = []

    chunks = output.get("chunks") or output.get("source_chunks") or []
    for chunk in chunks:
        sources.append({
            "recipe": chunk.recipe_name,
            "component": chunk.component_name,
            "file": chunk.source_file,
        })

    return sources

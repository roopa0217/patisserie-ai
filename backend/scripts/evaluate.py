"""
Evaluation script for Pâtisserie AI.

Tests 15 queries covering all four use cases plus edge cases.
Requires the backend to be running at http://localhost:8000.

Usage:
    python -m scripts.evaluate
    python -m scripts.evaluate --url http://localhost:8000 --out report.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime

import httpx

DEFAULT_URL = "http://localhost:8000"

# ── Test cases ────────────────────────────────────────────────────────────────

@dataclass
class TestCase:
    id: str
    use_case: str
    query: str
    expected_intent: str
    expect_low_confidence: bool = False
    expect_anomaly_fail: bool = False
    expect_anomaly_pass: bool = False
    expect_non_linear_warning: bool = False
    expect_indent_sheet: bool = False
    notes: str = ""


TEST_CASES: list[TestCase] = [
    # ── FIND RECIPE ──────────────────────────────────────────────────────────
    TestCase(
        id="FR-01",
        use_case="find_recipe",
        query="Show me the croissant recipe",
        expected_intent="find_recipe",
        notes="Should find croissant with lamination details",
    ),
    TestCase(
        id="FR-02",
        use_case="find_recipe",
        query="What recipes use mascarpone?",
        expected_intent="find_recipe",
        notes="Ingredient-based search",
    ),
    TestCase(
        id="FR-03",
        use_case="find_recipe",
        query="Show me an Italian beginner recipe",
        expected_intent="find_recipe",
        notes="Cuisine + difficulty filter",
    ),
    TestCase(
        id="FR-04",
        use_case="find_recipe",
        query="Quantum entanglement soufflé recipe",
        expected_intent="find_recipe",
        expect_low_confidence=True,
        notes="Recipe that does not exist — expect confident refusal",
    ),
    TestCase(
        id="FR-05",
        use_case="find_recipe",
        query="Find me a recipe using gelatine and passion fruit",
        expected_intent="find_recipe",
        notes="Multi-ingredient search",
    ),

    # ── SCALE RECIPE ─────────────────────────────────────────────────────────
    TestCase(
        id="SR-01",
        use_case="scale_recipe",
        query="Scale the croissant dough to 5000g",
        expected_intent="scale_recipe",
        expect_non_linear_warning=True,
        notes="Yeast and salt are non-linear — warnings expected",
    ),
    TestCase(
        id="SR-02",
        use_case="scale_recipe",
        query="Double the soft rolls recipe",
        expected_intent="scale_recipe",
        expect_non_linear_warning=True,
        notes="Scaling with yeast and salt",
    ),
    TestCase(
        id="SR-03",
        use_case="scale_recipe",
        query="Scale panna cotta for 50 portions",
        expected_intent="scale_recipe",
        expect_non_linear_warning=True,
        notes="Gelatin scale warning expected",
    ),
    TestCase(
        id="SR-04",
        use_case="scale_recipe",
        query="Scale a non-existent recipe to 1000g",
        expected_intent="scale_recipe",
        expect_low_confidence=True,
        notes="Recipe not in knowledge base — should error cleanly",
    ),

    # ── INDENT SHEET ─────────────────────────────────────────────────────────
    TestCase(
        id="IS-01",
        use_case="build_indent",
        query="Build an indent sheet for croissants and soft rolls",
        expected_intent="build_indent",
        expect_indent_sheet=True,
        notes="Multi-recipe consolidation",
    ),
    TestCase(
        id="IS-02",
        use_case="build_indent",
        query="Prep list for the whole Basics in Bread class",
        expected_intent="build_indent",
        expect_indent_sheet=True,
        notes="Class-level aggregation",
    ),

    # ── ANOMALY CHECK ─────────────────────────────────────────────────────────
    TestCase(
        id="AC-01",
        use_case="check_anomaly",
        query="Check the dark chocolate tart for ratio errors",
        expected_intent="check_anomaly",
        expect_anomaly_fail=True,
        notes="Chocolate glaze gelatin at ~4% exceeds 3% limit — should FAIL",
    ),
    TestCase(
        id="AC-02",
        use_case="check_anomaly",
        query="Validate the vanilla panna cotta recipe",
        expected_intent="check_anomaly",
        expect_anomaly_pass=True,
        notes="Gelatin at ~1.8% of liquid — should PASS",
    ),
    TestCase(
        id="AC-03",
        use_case="check_anomaly",
        query="Check the croissant dough for anomalies",
        expected_intent="check_anomaly",
        notes="No gelatin/chocolate rules apply — should report nothing to flag",
    ),

    # ── GENERAL KNOWLEDGE ────────────────────────────────────────────────────
    TestCase(
        id="GK-01",
        use_case="general",
        query="Why does lamination butter need to be the same consistency as the dough?",
        expected_intent="general",
        notes="Baking science question — should draw from ingested content",
    ),
    TestCase(
        id="GK-02",
        use_case="general",
        query="What temperature should I proof croissants at?",
        expected_intent="general",
        notes="Technique question — answer should be in the PDF",
    ),
]


# ── Result dataclass ──────────────────────────────────────────────────────────

@dataclass
class TestResult:
    test: TestCase
    intent_classified: str = ""
    confidence: float = 0.0
    result_type: str = ""
    low_confidence_received: bool = False
    anomaly_pass_received: bool = False
    anomaly_fail_received: bool = False
    non_linear_warning_received: bool = False
    indent_sheet_received: bool = False
    error: str = ""
    latency_ms: int = 0
    passed: bool = False
    failure_reason: str = ""


# ── HTTP helpers ──────────────────────────────────────────────────────────────

def _stream_chat(base_url: str, query: str) -> dict:
    """Call /chat/stream and collect all events. Returns parsed event dict."""
    events: list[dict] = []
    tokens: list[str] = []

    with httpx.Client(timeout=120) as client:
        with client.stream(
            "POST",
            f"{base_url}/chat/stream",
            json={"message": query, "history": []},
        ) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if line.startswith("data: "):
                    try:
                        event = json.loads(line[6:])
                        events.append(event)
                        if event.get("type") == "token":
                            tokens.append(event.get("content", ""))
                    except json.JSONDecodeError:
                        pass

    result = {
        "events": events,
        "full_text": "".join(tokens),
        "intent": "",
        "confidence": 0.0,
        "result_type": "",
        "result_data": None,
        "low_confidence": False,
    }

    for event in events:
        if event.get("type") == "meta":
            meta = event.get("content", {})
            result["intent"] = meta.get("intent", "")
            result["confidence"] = meta.get("confidence", 0.0)
        elif event.get("type") == "result":
            content = event.get("content", {})
            result["result_type"] = content.get("type", "")
            result["result_data"] = content.get("data")
        elif event.get("type") == "status":
            if "not found" in (event.get("content") or "").lower():
                result["low_confidence"] = True

    # Also detect low confidence from response text
    text_lower = result["full_text"].lower()
    if any(phrase in text_lower for phrase in [
        "not found", "couldn't find", "no reliable", "please upload",
        "not in the knowledge base",
    ]):
        result["low_confidence"] = True

    return result


# ── Evaluate a single test ────────────────────────────────────────────────────

def _evaluate_test(base_url: str, test: TestCase) -> TestResult:
    result = TestResult(test=test)
    start = time.time()

    try:
        raw = _stream_chat(base_url, test.query)
    except Exception as e:
        result.error = str(e)
        result.passed = False
        result.failure_reason = f"HTTP error: {e}"
        return result

    result.latency_ms = int((time.time() - start) * 1000)
    result.intent_classified = raw["intent"]
    result.confidence = raw["confidence"]
    result.result_type = raw["result_type"]
    result.low_confidence_received = raw["low_confidence"]

    # Check result data
    data = raw.get("result_data")
    if result.result_type == "anomaly_report" and data:
        results_list = data.get("results", [])
        has_fail = any(not r.get("passed") for r in results_list)
        has_pass = all(r.get("passed") for r in results_list) if results_list else False
        result.anomaly_fail_received = has_fail
        result.anomaly_pass_received = has_pass

    if result.result_type == "scale_results" and data:
        for component in data:
            if component.get("warnings"):
                result.non_linear_warning_received = True

    if result.result_type == "indent_sheet":
        result.indent_sheet_received = bool(data and data.get("rows"))

    # Check text for non-linear warnings
    full_text_lower = raw["full_text"].lower()
    if "⚠" in raw["full_text"] or "non-linear" in full_text_lower or "warning" in full_text_lower:
        result.non_linear_warning_received = True

    # ── Pass/Fail logic ───────────────────────────────────────────────────────
    failures = []

    if test.expected_intent and result.intent_classified != test.expected_intent:
        failures.append(
            f"Intent: expected '{test.expected_intent}', got '{result.intent_classified}'"
        )

    if test.expect_low_confidence and not result.low_confidence_received:
        failures.append("Expected low-confidence / not-found response but got confident answer")

    if not test.expect_low_confidence and result.low_confidence_received and result.confidence < 0.2:
        failures.append(f"Unexpected low confidence: {result.confidence:.2f}")

    if test.expect_anomaly_fail and not result.anomaly_fail_received:
        failures.append("Expected anomaly FAIL result but no failures were reported")

    if test.expect_anomaly_pass and result.anomaly_fail_received:
        failures.append("Expected anomaly PASS but failures were reported")

    if test.expect_non_linear_warning and not result.non_linear_warning_received:
        failures.append("Expected non-linear scaling warning but none was emitted")

    if test.expect_indent_sheet and not result.indent_sheet_received:
        failures.append("Expected structured indent sheet but none was returned")

    result.passed = len(failures) == 0
    result.failure_reason = "; ".join(failures)
    return result


# ── Report ────────────────────────────────────────────────────────────────────

def _print_report(results: list[TestResult]) -> None:
    passed = sum(1 for r in results if r.passed)
    total = len(results)
    score_pct = round(passed / total * 100) if total else 0

    print("\n" + "=" * 70)
    print(f"  PÂTISSERIE AI — EVALUATION REPORT  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 70)
    print(f"  Score: {passed}/{total}  ({score_pct}%)")
    print("=" * 70)

    use_cases = {}
    for r in results:
        uc = r.test.use_case
        use_cases.setdefault(uc, []).append(r)

    for uc, uc_results in use_cases.items():
        uc_passed = sum(1 for r in uc_results if r.passed)
        print(f"\n  ■ {uc.upper()}  ({uc_passed}/{len(uc_results)})")
        for r in uc_results:
            icon = "✓" if r.passed else "✗"
            conf = f"{r.confidence:.2f}" if r.confidence else "n/a"
            latency = f"{r.latency_ms}ms"
            print(f"    {icon}  [{r.test.id}]  {r.test.query[:55]:<55}  conf={conf}  {latency}")
            if not r.passed:
                print(f"         FAIL: {r.failure_reason}")
            if r.error:
                print(f"         ERROR: {r.error}")

    if passed < total:
        print("\n  ── FAILURE ANALYSIS ──────────────────────────────────────────")
        for r in results:
            if not r.passed:
                print(f"\n  [{r.test.id}] {r.test.query}")
                print(f"    Use case:  {r.test.use_case}")
                print(f"    Intent:    expected={r.test.expected_intent}  got={r.intent_classified}")
                print(f"    Failure:   {r.failure_reason}")
                print(f"    Notes:     {r.test.notes}")

    print("\n" + "=" * 70 + "\n")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Evaluate Pâtisserie AI")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--out", default=None, help="Write JSON report to file")
    parser.add_argument("--ids", nargs="*", help="Run only specific test IDs")
    args = parser.parse_args()

    cases = TEST_CASES
    if args.ids:
        cases = [t for t in TEST_CASES if t.id in args.ids]

    # Health check
    try:
        r = httpx.get(f"{args.url}/health", timeout=5)
        r.raise_for_status()
    except Exception as e:
        print(f"ERROR: Backend not reachable at {args.url} — {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Running {len(cases)} tests against {args.url} ...")
    results = []
    for i, test in enumerate(cases, 1):
        print(f"  [{i}/{len(cases)}] {test.id}: {test.query[:60]}", end="", flush=True)
        r = _evaluate_test(args.url, test)
        icon = "✓" if r.passed else "✗"
        print(f"  {icon}  ({r.latency_ms}ms)")
        results.append(r)

    _print_report(results)

    if args.out:
        report_data = {
            "timestamp": datetime.now().isoformat(),
            "score": f"{sum(1 for r in results if r.passed)}/{len(results)}",
            "tests": [
                {
                    "id": r.test.id,
                    "use_case": r.test.use_case,
                    "query": r.test.query,
                    "intent_classified": r.intent_classified,
                    "confidence": r.confidence,
                    "passed": r.passed,
                    "failure_reason": r.failure_reason,
                    "latency_ms": r.latency_ms,
                }
                for r in results
            ],
        }
        with open(args.out, "w") as f:
            json.dump(report_data, f, indent=2)
        print(f"Report written to {args.out}")


if __name__ == "__main__":
    main()

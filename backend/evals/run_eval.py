"""Agent Answer Evaluation suite.

Asks the real agent (chat ReAct, or the Cost Saving/Forecast/Contract Risk
agent) every question in questions.yaml and checks the reply against a
ground truth computed independently of any LLM - see questions.yaml's
header for the three ways a ground truth is derived (raw SQL, the exact
deterministic function the app itself uses, or a known fact about the
fixture). Complements scripts/evaluate_rag.py, which measures retrieval/
relevance quality via embedding similarity rather than numeric correctness
against a known answer - this script is the "does the number match the
official report" check instead.

Usage:
    python evals/run_eval.py [--report path.md] [--json path.json] [--fail-under 0.75]

Builds its own isolated SQLite database (see fixtures.py) - safe to run
anywhere, including CI, without a real Postgres/Qdrant/LLM provider
configured. If no LLM provider is reachable (no GROQ_API_KEY, no local
Ollama), every agent reply falls back to the deterministic offline stub
(app/services/ai.py::_offline_fallback) and will fail nearly every
question - the run is then marked "degraded" instead of a hard failure,
since that outcome reflects missing infrastructure, not an agent
regression. The same applies if a free-tier provider (Groq) rate-limits
the run partway through (HTTP 429) - a single up-front reachability check
can't catch that, since it happens only after burning through the quota
over the many ReAct calls this suite makes, so the actual run is also
scanned afterwards for the offline stub's output (see _OFFLINE_PREFIX)
and marked degraded retroactively if most replies ended up there. A
small delay between questions (see _INTER_QUESTION_DELAY_SECONDS) also
reduces how often this happens in the first place.
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
import re
import sys
import tempfile
import time
import unicodedata
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND_ROOT))

# Must happen before any `from app...` import: app.core.database builds its
# engine/SessionLocal from settings.database_url at import time, and every
# standalone entry point this script drives (chat_service.answer_question,
# cost_saving_agent.analyze) opens its own SessionLocal() rather than
# taking an injected session - so the only way to point the whole app at
# this script's isolated fixture DB is this environment variable, set
# before app.core.config.Settings() ever runs.
_DB_PATH = Path(tempfile.gettempdir()) / "spendintel_eval.db"
if _DB_PATH.exists():
    _DB_PATH.unlink()
os.environ["DATABASE_URL"] = f"sqlite:///{_DB_PATH}"
os.environ.setdefault("OLLAMA_TIMEOUT", "2")  # fail fast if no local Ollama

import yaml  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.core.database import Base, SessionLocal, engine  # noqa: E402
from app.services import chat_service, cost_saving_agent  # noqa: E402
from evals import fixtures  # noqa: E402

_QUESTIONS_PATH = Path(__file__).parent / "questions.yaml"
_NUMBER_RE = re.compile(r"-?\d[\d.,]*\d|\d")
_OFFLINE_PREFIX = "[Offline]"  # ai.py::_offline_fallback's distinctive marker
_OFFLINE_FRACTION_DEGRADED_THRESHOLD = 0.3
_INTER_QUESTION_DELAY_SECONDS = 2.0  # stay under a free-tier provider's rate limit


def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def _extract_number(text_: str) -> float | None:
    """Best-effort extraction of the first number in a free-text reply,
    handling both '1,234.56' (US) and '1.234,56' (EU) formatting. This is
    a heuristic, not a parser - good enough to check an LLM's rendering of
    a number a tool already computed, not meant as a general-purpose
    number parser (surfaced raw in the report for a human to double-check
    any surprising miss)."""
    match = _NUMBER_RE.search(text_.replace("€", ""))
    if not match:
        return None
    raw = match.group(0)
    if "," in raw and "." in raw:
        raw = raw.replace(".", "").replace(",", ".") if raw.rfind(",") > raw.rfind(".") else raw.replace(",", "")
    elif "," in raw:
        raw = raw.replace(",", ".") if re.search(r",\d{1,2}$", raw) else raw.replace(",", "")
    try:
        return float(raw)
    except ValueError:
        return None


def _numbers_match(expected: float, actual: float | None, tolerance_pct: float | None, tolerance_abs: float | None) -> bool:
    if actual is None:
        return False
    if tolerance_abs is not None:
        return abs(expected - actual) <= tolerance_abs
    tol_pct = tolerance_pct if tolerance_pct is not None else 2.0
    if expected == 0:
        return abs(actual) <= max(tol_pct, 1.0)
    return abs(expected - actual) / abs(expected) <= tol_pct / 100.0


def _contains(haystack: str, needle: str) -> bool:
    return _strip_accents(needle.lower()) in _strip_accents((haystack or "").lower())


def _resolve_dotted(path: str):
    module_path, _, attr = path.rpartition(".")
    return getattr(importlib.import_module(module_path), attr)


def _providers_available() -> bool:
    """Whether the full chat() provider chain (Ollama -> Groq -> offline
    stub, app/services/ai.py) actually produces a real reply, not just
    whether Ollama's HTTP server happens to be reachable - a reachable
    Ollama with the configured model not pulled still falls through to the
    offline stub, which a plain /api/tags ping would miss entirely."""
    from app.services.ai import chat as llm_chat
    reply = llm_chat([{"role": "user", "content": "ping"}])
    return not reply.startswith("[Offline]")


def _ground_truth(q: dict, db, buyer_id: int):
    """Resolves a computed ground truth from expected_sql/reference_fn/
    expected_literal. A question that only carries expected_any (a fixed
    list of acceptable substrings - see questions.yaml's header) needs no
    separately computed `expected`, since the list itself already is the
    ground truth; returning None there is correct, not a missing case."""
    if "expected_sql" in q:
        row = db.execute(text(q["expected_sql"]), {"buyer_id": buyer_id}).first()
        return row[0] if row else None
    if "reference_fn" in q:
        fn = _resolve_dotted(q["reference_fn"])
        result = fn(user_id=buyer_id, db=db)
        if "reference_key" in q:
            match = next((r for r in result if r[q["reference_key"]] == q["reference_match"]), None)
            return match[q["reference_field"]] if match else None
        if isinstance(result, dict) and "reference_field" in q:
            return result[q["reference_field"]]
        return result
    if "expected_literal" in q:
        return q["expected_literal"]
    if "expected_any" in q:
        return None
    raise ValueError(f"Question {q['id']} has no ground truth source (expected_sql/reference_fn/expected_literal/expected_any)")


def _ask_agent(q: dict, buyer_id: int) -> str:
    lang = "it"
    if q["target"] == "chat":
        result = chat_service.answer_question(
            q["question"], session_id=None, user_id=buyer_id, lang=lang, visible_user_ids=buyer_id,
        )
        return result["reply"]
    db = SessionLocal()
    try:
        run = cost_saving_agent.analyze(
            q["question"], user_id=buyer_id, db=db, agent_type=q["target"], lang=lang, visible_user_ids=buyer_id,
        )
        return run.summary or ""
    finally:
        db.close()


def _evaluate_one(q: dict, db, buyer_id: int) -> dict:
    expected = _ground_truth(q, db, buyer_id)
    reply = _ask_agent(q, buyer_id)
    compare = q["compare"]
    if compare == "numeric":
        actual = _extract_number(reply)
        passed = _numbers_match(float(expected), actual, q.get("tolerance_pct"), q.get("tolerance_abs"))
    elif compare == "contains_any":
        candidates = q.get("expected_any") or ([str(expected)] if expected is not None else [])
        passed = any(_contains(reply, c) for c in candidates)
        actual = reply
    elif compare == "contains":
        needle = q.get("expected_literal", str(expected))
        passed = _contains(reply, needle)
        actual = reply
    else:
        raise ValueError(f"Unknown compare mode: {compare}")
    return {
        "id": q["id"], "question": q["question"], "target": q["target"], "compare": compare,
        "expected": expected, "actual": actual, "reply": reply, "passed": passed,
    }


def run(fail_under: float, report_path: str | None, json_path: str | None) -> int:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        buyer_id = fixtures.seed(db)["buyer_id"]
        questions = yaml.safe_load(_QUESTIONS_PATH.read_text(encoding="utf-8"))["questions"]
        degraded = not _providers_available()
        results = []
        for i, q in enumerate(questions):
            if i > 0:
                time.sleep(_INTER_QUESTION_DELAY_SECONDS)
            results.append(_evaluate_one(q, db, buyer_id))
    finally:
        db.close()

    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    pass_rate = passed / total if total else 0.0

    # A single up-front availability ping can succeed and then the run
    # still burns through a free-tier provider's rate limit partway
    # through (HTTP 429 - see ai.py's broad except around every Groq
    # call), silently falling back to the offline stub for the rest of
    # the run. Catch that after the fact by checking what actually came
    # back, instead of trusting only the point-in-time check above.
    offline_replies = sum(1 for r in results if (r.get("reply") or "").startswith(_OFFLINE_PREFIX))
    if total and offline_replies / total >= _OFFLINE_FRACTION_DEGRADED_THRESHOLD:
        degraded = True

    _print_console_summary(results, pass_rate, degraded)
    if report_path:
        _write_markdown_report(report_path, results, pass_rate, degraded)
    if json_path:
        Path(json_path).write_text(
            json.dumps({"pass_rate": pass_rate, "degraded": degraded, "results": results}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    if degraded:
        print(
            "\nNo LLM provider reachable (GROQ_API_KEY unset, Ollama unreachable) - "
            "run marked degraded, not failing the build on pass rate alone."
        )
        return 0
    return 0 if pass_rate >= fail_under else 1


def _print_console_summary(results: list[dict], pass_rate: float, degraded: bool) -> None:
    print("=" * 60)
    print("  Agent Answer Evaluation")
    print("=" * 60)
    for r in results:
        mark = "PASS" if r["passed"] else "FAIL"
        print(f"[{mark}] {r['id']:<32} ({r['target']:<13}) expected={r['expected']!r}")
    print("-" * 60)
    suffix = "  [DEGRADED: no LLM provider reachable]" if degraded else ""
    print(f"Pass rate: {pass_rate:.1%} ({sum(1 for r in results if r['passed'])}/{len(results)}){suffix}")


def _write_markdown_report(path: str, results: list[dict], pass_rate: float, degraded: bool) -> None:
    lines = ["# Agent Answer Evaluation Report", ""]
    if degraded:
        lines += [
            "> **Degraded run**: no LLM provider was reachable (no `GROQ_API_KEY`, no local "
            "Ollama) - replies came from the offline fallback stub, so most questions are "
            "expected to fail. This does not reflect an agent regression.",
            "",
        ]
    passed = sum(1 for r in results if r["passed"])
    lines += [f"**Pass rate: {pass_rate:.1%}** ({passed}/{len(results)})", ""]
    lines += ["| id | target | result | expected | agent reply |", "|---|---|---|---|---|"]
    for r in results:
        mark = "PASS" if r["passed"] else "FAIL"
        reply = (r["reply"] or "").replace("\n", " ").replace("|", "\\|")[:200]
        lines.append(f"| {r['id']} | {r['target']} | {mark} | {r['expected']!r} | {reply} |")
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Agent Answer Evaluation suite")
    parser.add_argument("--report", help="Write a Markdown report to this path")
    parser.add_argument("--json", help="Write a JSON report to this path")
    parser.add_argument(
        "--fail-under", type=float, default=0.75,
        help="Exit non-zero if pass rate is below this (ignored on a degraded run)",
    )
    args = parser.parse_args()
    sys.exit(run(args.fail_under, args.report, args.json))


if __name__ == "__main__":
    main()

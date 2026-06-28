"""Agent-level evaluation with a self-correction retry loop.

For each question we:
1. run the agent (mock by default, real Claude if ANTHROPIC_API_KEY is set),
2. check it called the expected tool,
3. extract the numeric answer and compare to ground truth computed by the SAME
   risk engine the tools use (on deterministic mock data),
4. on failure, re-prompt once with a corrective hint and re-score.

Run:  python -m evals.run_evals
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

# Force deterministic, offline mode so grading is reproducible even though the
# app defaults to live data. (config reads these flags at call time.)
os.environ.setdefault("USE_MOCK_DATA", "1")
os.environ.setdefault("USE_MOCK_LLM", "auto")

from portfolio_risk import config, tools  # noqa: E402
from portfolio_risk.agent.client import run_agent  # noqa: E402

from .groundedness import evaluate as evaluate_groundedness  # noqa: E402
from .report import render_detail, render_report  # noqa: E402

QUESTIONS = Path(__file__).parent / "questions.jsonl"

_TRUTH_FNS = {
    "get_stock_snapshot": tools.get_stock_snapshot,
    "get_price_performance": tools.get_price_performance,
    "explain_stock_risk": tools.explain_stock_risk,
    "get_technical_indicators": tools.get_technical_indicators,
    "explain_price_move": tools.explain_price_move,
    "get_portfolio_overview": tools.get_portfolio_overview,
    "get_portfolio_risk_report": tools.get_portfolio_risk_report,
    "run_portfolio_scenario": tools.run_portfolio_scenario,
    "get_portfolio_briefing": tools.get_portfolio_briefing,
}


def compute_truth(spec: dict) -> float:
    out = _TRUTH_FNS[spec["fn"]](**spec["args"])
    if "error" in out:
        raise RuntimeError(f"truth computation failed: {out['error']}")
    return float(out[spec["field"]])


def extract_value(text: str, unit: str):
    if unit == "fraction_pct":
        # Prefer a (possibly signed) percentage with a decimal point (the metric
        # value, e.g. "-1.23%") over a bare integer percentage. Fall back to any
        # percentage. Sign matters for things like a down-day change.
        m = re.search(r"(-?\d+\.\d+)\s*%", text) or re.search(r"(-?\d+(?:\.\d+)?)\s*%", text)
        return float(m.group(1)) / 100.0 if m else None
    # raw decimal number (requires a decimal point to skip years/counts)
    m = re.search(r"(-?\d+\.\d+)", text)
    return float(m.group(1)) if m else None


def score(result, q) -> dict:
    tool_ok = q["expected_tool"] in result.tool_names()
    truth = q.get("truth")
    if truth is None:
        return {
            "tool_ok": tool_ok,
            "num_ok": True,
            "passed": tool_ok,
            "truth": None,
            "agent_value": None,
        }
    truth_val = compute_truth(truth)
    agent_val = extract_value(result.answer, truth["unit"])
    num_ok = agent_val is not None and abs(agent_val - truth_val) <= q["tolerance"]
    return {
        "tool_ok": tool_ok,
        "num_ok": num_ok,
        "passed": tool_ok and num_ok,
        "truth": truth_val,
        "agent_value": agent_val,
    }


def correction_hint(q, sc) -> str:
    unit = "a percentage" if (q.get("truth") or {}).get("unit") == "fraction_pct" else "a number"
    return (
        f"Your previous response did not pass automated checks. Use the "
        f"`{q['expected_tool']}` tool and state the numeric result explicitly as {unit}."
    )


def main() -> None:
    # Portfolio questions run against a deterministic seeded portfolio in a
    # temp DB, so truth and agent answers compute from identical state without
    # touching the user's real data/portfolio.db.
    import tempfile
    from pathlib import Path as _Path

    tmp_db = _Path(tempfile.mkdtemp(prefix="evals_portfolio_")) / "portfolio.db"
    os.environ["PORTFOLIO_DB_URL"] = f"sqlite:///{tmp_db.as_posix()}"
    from portfolio_risk.portfolio.db import reset_engine

    reset_engine()
    from .seed_portfolio import ensure_seeded

    ensure_seeded()

    mode = "mock agent" if config.use_mock_llm() else f"Claude ({config.MODEL})"
    questions = [
        json.loads(line) for line in QUESTIONS.read_text(encoding="utf-8").splitlines() if line.strip()
    ]

    rows: list[dict] = []
    for q in questions:
        result = run_agent(q["question"])
        sc = score(result, q)
        passed_after = sc["passed"]
        if not sc["passed"]:
            retry = run_agent(q["question"] + "\n\n[Correction] " + correction_hint(q, sc))
            sc_retry = score(retry, q)
            passed_after = sc_retry["passed"]
            result = retry if sc_retry["passed"] else result

        ground = evaluate_groundedness(result)
        rows.append(
            {
                "id": q["id"],
                "question": q["question"],
                "tool_ok": sc["tool_ok"],
                "num_ok": sc["num_ok"],
                "passed": sc["passed"],
                "passed_after_retry": passed_after,
                "truth": sc["truth"],
                "agent_value": sc["agent_value"],
                "tolerance": q.get("tolerance"),
                "tool_names": result.tool_names(),
                "answer": result.answer,
                "groundedness": ground["groundedness"],
                "ground_method": ground["method"],
                "citations_ok": ground["citations_ok"],
                "ground_sources": ground["sources"],
                "fabricated_citations": ground["fabricated_citations"],
                "unsupported_claims": ground["unsupported_claims"],
                "has_evidence": ground["has_evidence"],
            }
        )

    print(render_report(rows, mode))
    print(render_detail(rows))


if __name__ == "__main__":
    main()

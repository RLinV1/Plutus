"""Offline tests for the RAG groundedness checker (citation + faithfulness)."""

from __future__ import annotations

from evals import groundedness as gd
from portfolio_risk.agent.base import AgentResult


def _result(answer: str, results: list[dict]) -> AgentResult:
    return AgentResult(
        answer=answer,
        tool_calls=[
            {"name": "search_knowledge", "input": {"query": "x"}, "output": {"results": results}}
        ],
    )


def test_source_link_seed_and_edgar():
    assert gd._source_link("AAPL_profile.md").endswith("seed/AAPL_profile.md")
    assert "sec.gov" in gd._source_link("SEC EDGAR 10-K (AAPL)", "AAPL")
    assert gd._source_link("") == ""


def test_collect_evidence_uses_captured_output_and_adds_links():
    res = _result("ans", [{"text": "a P/E ratio compares price to earnings", "source": "GENERAL_investing_basics.md"}])
    ev = gd.collect_evidence(res)
    assert len(ev) == 1
    assert ev[0]["source"] == "GENERAL_investing_basics.md"
    assert ev[0]["url"].endswith("seed/GENERAL_investing_basics.md")


def test_citations_ok_when_cited_source_was_retrieved():
    res = _result(
        "A P/E ratio compares price to earnings [GENERAL_investing_basics.md].",
        [{"text": "the P/E ratio compares price to earnings", "source": "GENERAL_investing_basics.md"}],
    )
    rep = gd.evaluate(res)
    assert rep["has_evidence"] is True
    assert rep["citations_ok"] is True
    assert rep["fabricated_citations"] == []
    assert any(s["url"] for s in rep["sources"])  # link present


def test_fabricated_citation_is_flagged():
    res = _result(
        "Trust me, this is true [TOTALLY_MADE_UP.md].",
        [{"text": "real chunk", "source": "GENERAL_investing_basics.md"}],
    )
    rep = gd.evaluate(res)
    assert "TOTALLY_MADE_UP.md" in rep["fabricated_citations"]
    assert rep["citations_ok"] is False


def test_faithfulness_lexical_is_deterministic_offline():
    ev = [{"text": "volatility measures how much a price swings", "source": "s.md", "url": ""}]
    a = gd.faithfulness("volatility measures how much a price swings", ev)
    b = gd.faithfulness("volatility measures how much a price swings", ev)
    assert a["method"] == "lexical"
    assert a["score"] == b["score"]
    assert a["score"] > 0.5


def test_no_evidence_means_no_groundedness():
    res = AgentResult(answer="hi", tool_calls=[{"name": "get_stock_snapshot", "input": {}, "output": {}}])
    rep = gd.evaluate(res)
    assert rep["has_evidence"] is False
    assert rep["groundedness"] is None

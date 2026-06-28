"""Groundedness checks for RAG-backed answers — does the AI stick to its sources?

Two independent checks over an ``AgentResult``:

1. **Citation check** (deterministic, always runs): every ``[source]`` the answer
   cites must be a source actually returned by a retrieval tool in this run.
   Flags fabricated citations and uncited RAG answers.
2. **Faithfulness** (LLM-as-judge): rate how well the answer is supported by the
   retrieved chunks (0–1). Uses real Claude when a key is present; falls back to a
   deterministic lexical-overlap proxy offline (so CI/evals still produce a score).

Every supported source is reported **with a link** (SEC URL for filings, article
URL for news, repo path for the seed corpus) so the proof is verifiable.

Evidence is taken from each tool call's captured ``output`` when present, and
re-derived deterministically from the call's ``input`` otherwise (retrieval is
deterministic), so this works for both the mock agent and the real Claude path.
"""

from __future__ import annotations

import json
import re

from portfolio_risk import config

# Tools whose output is retrieved knowledge we can check an answer against.
RAG_TOOLS = {"search_knowledge", "get_filing_risks"}

# Words too common to count as evidence of overlap in the offline proxy.
_STOPWORDS = frozenset(
    """a an the of to in on for and or is it its as at by be are was were this that
    these those with from into over under about than then so such not no your you we
    our their his her they i me my will would can could should may might also more
    most very just only but if while which who whom what when where how why per each
    any all some one two stock stocks company companies price prices market""".split()
)

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'-]+")
# Bracketed citations that look like a source: a filename or an EDGAR/SEC marker.
_CITE_RE = re.compile(
    r"\[([^\[\]]*?(?:\.(?:md|txt|html?|pdf)|EDGAR|SEC|10-K)[^\[\]]*?)\]", re.IGNORECASE
)


# --------------------------------------------------------------------------- #
# Evidence collection
# --------------------------------------------------------------------------- #
def _results_from(out) -> list[dict]:
    """Normalize a retrieval tool's output into [{text, source, url}] rows."""
    if isinstance(out, str):
        try:
            out = json.loads(out)
        except Exception:  # noqa: BLE001
            return []
    if not isinstance(out, dict):
        return []
    rows = out.get("results") or out.get("chunks") or []
    norm: list[dict] = []
    for r in rows:
        if isinstance(r, dict):
            norm.append(
                {
                    "text": r.get("text", ""),
                    "source": r.get("source", ""),
                    "url": r.get("url", "") or r.get("link", ""),
                    "ticker": r.get("ticker", ""),
                }
            )
        elif isinstance(r, str):
            norm.append({"text": r, "source": "", "url": "", "ticker": ""})
    return norm


def collect_evidence(result) -> list[dict]:
    """Gather the retrieved chunks the agent had access to, de-duplicated."""
    from portfolio_risk import tools as _tools

    evidence: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for call in getattr(result, "tool_calls", []):
        if call.get("name") not in RAG_TOOLS:
            continue
        out = call.get("output")
        if not out:  # real-Claude path may not capture it — re-derive deterministically
            fn = getattr(_tools, call["name"], None)
            try:
                out = fn(**call.get("input", {})) if fn else None
            except Exception:  # noqa: BLE001
                out = None
        for row in _results_from(out):
            key = (row["source"], row["text"][:80])
            if key in seen:
                continue
            seen.add(key)
            if not row.get("url"):
                row["url"] = _source_link(row["source"], row.get("ticker", ""))
            evidence.append(row)
    return evidence


def _source_link(source: str, ticker: str = "") -> str:
    """Best-effort link to where a source came from (so proof is verifiable)."""
    if not source:
        return ""
    low = source.lower()
    if low.endswith((".md", ".txt")):
        return f"src/portfolio_risk/rag/seed/{source}"
    if "edgar" in low or "sec" in low or "10-k" in low:
        t = (ticker or "").upper()
        if t:
            return f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&ticker={t}&type=10-K"
        return "https://www.sec.gov/edgar/search/"
    return ""


# --------------------------------------------------------------------------- #
# Check 1: citation verification (deterministic)
# --------------------------------------------------------------------------- #
def check_citations(answer: str, evidence: list[dict]) -> dict:
    """Confirm every cited source was actually retrieved; flag fabrications."""
    cited = {m.strip() for m in _CITE_RE.findall(answer or "")}
    available = {e["source"] for e in evidence if e["source"]}

    def _match(c: str) -> bool:
        return any(c == a or c in a or a in c for a in available)

    fabricated = sorted(c for c in cited if not _match(c))
    matched = sorted(c for c in cited if _match(c))
    # OK when: nothing fabricated, AND if we have evidence the answer cites it.
    ok = not fabricated and (bool(matched) if evidence else True)
    return {
        "ok": ok,
        "cited": sorted(cited),
        "matched": matched,
        "fabricated": fabricated,
        "uncited": bool(evidence) and not cited,
    }


# --------------------------------------------------------------------------- #
# Check 2: faithfulness (LLM-as-judge, with offline lexical fallback)
# --------------------------------------------------------------------------- #
def _lexical_faithfulness(answer: str, evidence: list[dict]) -> dict:
    """Deterministic proxy: fraction of the answer's content words present in the
    retrieved text. Coarse, but reproducible offline."""
    ev_text = " ".join(e["text"] for e in evidence).lower()
    ev_words = set(_WORD_RE.findall(ev_text))
    ans_words = [
        w for w in (m.lower() for m in _WORD_RE.findall(answer or ""))
        if w not in _STOPWORDS and len(w) > 2
    ]
    if not ans_words:
        return {"score": None, "method": "lexical", "unsupported_claims": []}
    hits = sum(1 for w in ans_words if w in ev_words)
    return {
        "score": round(hits / len(ans_words), 3),
        "method": "lexical",
        "unsupported_claims": [],
    }


_JUDGE_PROMPT = """You are grading whether an ANSWER is faithful to its SOURCES \
(retrieved knowledge). A claim is "supported" only if a source states or directly \
implies it. General financial disclaimers and common-knowledge framing do not need \
support.

Return ONLY a JSON object:
{{"score": <0.0-1.0 fraction of substantive claims that are supported>,
  "unsupported_claims": [<short strings for any claims NOT supported by the sources>]}}

SOURCES:
{context}

ANSWER:
{answer}
"""


def _llm_faithfulness(answer: str, evidence: list[dict]) -> dict:
    """LLM-as-judge groundedness score. Falls back to lexical on any failure."""
    try:
        import anthropic

        context = "\n\n".join(
            f"[{i + 1}] (source: {e['source'] or 'unknown'})\n{e['text']}"
            for i, e in enumerate(evidence)
        )
        client = anthropic.Anthropic()
        msg = client.messages.create(
            model=config.MODEL,
            max_tokens=1024,
            messages=[
                {
                    "role": "user",
                    "content": _JUDGE_PROMPT.format(context=context, answer=answer),
                }
            ],
        )
        text = "".join(b.text for b in msg.content if getattr(b, "type", None) == "text")
        m = re.search(r"\{.*\}", text, re.DOTALL)
        data = json.loads(m.group(0)) if m else {}
        score = data.get("score")
        return {
            "score": round(float(score), 3) if score is not None else None,
            "method": "llm",
            "unsupported_claims": list(data.get("unsupported_claims", []))[:5],
        }
    except Exception:  # noqa: BLE001 — judging must never break the eval run
        return _lexical_faithfulness(answer, evidence)


def faithfulness(answer: str, evidence: list[dict]) -> dict:
    """Score how well the answer is supported by the evidence (0–1)."""
    if not evidence:
        return {"score": None, "method": "none", "unsupported_claims": []}
    # Offline (no key / forced mock LLM) → deterministic proxy; else LLM judge.
    if config.use_mock_llm():
        return _lexical_faithfulness(answer, evidence)
    return _llm_faithfulness(answer, evidence)


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #
def evaluate(result) -> dict:
    """Run both groundedness checks over an ``AgentResult``.

    Returns {has_evidence, citations_ok, fabricated_citations, groundedness,
    method, unsupported_claims, sources}. ``sources`` carries each retrieved
    source WITH a link so the proof is verifiable.
    """
    evidence = collect_evidence(result)
    cites = check_citations(getattr(result, "answer", ""), evidence)
    faith = faithfulness(getattr(result, "answer", ""), evidence)

    sources, seen = [], set()
    for e in evidence:
        if e["source"] and e["source"] not in seen:
            seen.add(e["source"])
            sources.append({"source": e["source"], "url": e["url"]})

    return {
        "has_evidence": bool(evidence),
        "citations_ok": cites["ok"],
        "fabricated_citations": cites["fabricated"],
        "groundedness": faith["score"],
        "method": faith["method"],
        "unsupported_claims": faith["unsupported_claims"],
        "sources": sources,
    }


def format_proof(report: dict) -> str:
    """Render a human-readable 'proof' block: score + sources WITH links."""
    if not report.get("has_evidence"):
        return "Groundedness: n/a (no retrieved sources)."
    score = report.get("groundedness")
    score_txt = f"{score:.0%}" if isinstance(score, (int, float)) else "n/a"
    lines = [f"Groundedness: {score_txt} ({report.get('method')} judge)."]
    if report["sources"]:
        lines.append("Sources:")
        for s in report["sources"]:
            link = f" — {s['url']}" if s["url"] else ""
            lines.append(f"  - [{s['source']}]{link}")
    if report["fabricated_citations"]:
        lines.append("⚠ Fabricated citations: " + ", ".join(report["fabricated_citations"]))
    if report["unsupported_claims"]:
        lines.append("⚠ Unsupported claims: " + "; ".join(report["unsupported_claims"]))
    return "\n".join(lines)

"""Pretty-print eval results."""

from __future__ import annotations


def render_report(rows: list[dict], mode: str) -> str:
    lines = [
        "",
        f"=== Agent eval report  (mode: {mode}) ===",
        "",
        f"{'id':<24}{'tool':<8}{'numeric':<10}{'pass':<7}{'after_retry':<12}{'ground':<8}{'cites':<7}",
        "-" * 76,
    ]
    first_pass = 0
    after_retry = 0
    for r in rows:
        tool = "ok" if r["tool_ok"] else "MISS"
        num = "ok" if r["num_ok"] else ("--" if r["truth"] is None else "MISS")
        p = "PASS" if r["passed"] else "fail"
        ar = ""
        if not r["passed"]:
            ar = "PASS" if r.get("passed_after_retry") else "fail"
        if r["passed"]:
            first_pass += 1
            after_retry += 1
        elif r.get("passed_after_retry"):
            after_retry += 1
        g = r.get("groundedness")
        ground = f"{g:.0%}" if isinstance(g, (int, float)) else "--"
        if r.get("has_evidence"):
            cites = "ok" if r.get("citations_ok") else "MISS"
        else:
            cites = "--"
        lines.append(
            f"{r['id']:<24}{tool:<8}{num:<10}{p:<7}{ar:<12}{ground:<8}{cites:<7}"
        )

    n = len(rows)
    lines += [
        "-" * 76,
        f"First-pass:   {first_pass}/{n}  ({first_pass / n * 100:.0f}%)" if n else "no questions",
    ]
    if n:
        lines.append(f"After retry:  {after_retry}/{n}  ({after_retry / n * 100:.0f}%)")
    lines.append("")
    return "\n".join(lines)


def render_detail(rows: list[dict]) -> str:
    out = ["Per-question detail:"]
    for r in rows:
        out.append(f"\n[{r['id']}] {r['question']}")
        out.append(f"  tools used : {', '.join(r['tool_names']) or '(none)'}")
        if r["truth"] is not None:
            out.append(
                f"  truth={r['truth']:.4f}  agent={r['agent_value']}  tol={r['tolerance']}"
            )
        if r.get("has_evidence"):
            g = r.get("groundedness")
            g_txt = f"{g:.0%}" if isinstance(g, (int, float)) else "n/a"
            out.append(f"  groundedness: {g_txt} ({r.get('ground_method')} judge)")
            for s in r.get("ground_sources", []):
                link = f" -> {s['url']}" if s.get("url") else ""
                out.append(f"    source: [{s['source']}]{link}")
            if r.get("fabricated_citations"):
                out.append("    ⚠ fabricated: " + ", ".join(r["fabricated_citations"]))
            if r.get("unsupported_claims"):
                out.append("    ⚠ unsupported: " + "; ".join(r["unsupported_claims"]))
        out.append(f"  answer     : {r['answer'][:160].splitlines()[0] if r['answer'] else ''}")
    return "\n".join(out)

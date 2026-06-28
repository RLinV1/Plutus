"""Generate a plain-English daily digest for a watchlist — built to be scheduled.

Composes each stock's recent move + same-window headlines (via the shared
``tools.get_watchlist_digest``) into a dated markdown brief under ``data/digests/``.
When a real Claude key is configured it adds an agent-written narrative; otherwise
it uses a deterministic template, so the script runs fully offline too.

Run once:
    python -m scripts.daily_digest AAPL MSFT NVDA
    python -m scripts.daily_digest --period 1w           # uses the saved watchlist

Schedule it (no new infra) with the /schedule routine or a cron entry, e.g. daily
at 8am:  0 8 * * *  python -m scripts.daily_digest

Watchlist source (first match wins): CLI tickers > data/watchlist.json (a JSON list)
> $STOCK_WATCHLIST (comma-separated) > a small default.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
from pathlib import Path

from portfolio_risk import config, tools

_DEFAULT = ["AAPL", "MSFT", "NVDA"]
_WATCHLIST_FILE = config.DATA_DIR / "watchlist.json"


def resolve_watchlist(cli_tickers: list[str]) -> list[str]:
    if cli_tickers:
        return [t.upper() for t in cli_tickers]
    if _WATCHLIST_FILE.exists():
        try:
            data = json.loads(_WATCHLIST_FILE.read_text(encoding="utf-8"))
            if isinstance(data, list) and data:
                return [str(t).upper() for t in data]
        except Exception as exc:  # noqa: BLE001
            print(f"  could not read {_WATCHLIST_FILE}: {exc}", file=sys.stderr)
    env = os.environ.get("STOCK_WATCHLIST", "").strip()
    if env:
        return [t.strip().upper() for t in env.split(",") if t.strip()]
    return _DEFAULT


def _narrative(digest: dict) -> str:
    """A short written brief. Uses real Claude when available, else a template."""
    items = digest.get("items", [])
    if not config.use_mock_llm():  # a key is set → let the agent write it
        try:
            from portfolio_risk.agent.client import run_agent

            tickers = ", ".join(i["ticker"] for i in items if "ticker" in i)
            q = (
                "Write a brief, friendly morning watchlist digest (a few sentences) "
                f"for these stocks: {tickers}. For each, explain its recent move using "
                "recent news, and reference the headlines. Keep it plain-English."
            )
            return run_agent(q).answer
        except Exception as exc:  # noqa: BLE001
            print(f"  agent narrative failed ({exc}); using template", file=sys.stderr)
    # Deterministic template fallback.
    bits = []
    for i in items:
        if "error" in i:
            continue
        bits.append(
            f"{i['ticker']} {i['direction']} {i['move_pct']:+.2f}% ({i['movement_label']})"
        )
    return "Watchlist at a glance: " + "; ".join(bits) + "." if bits else "No data."


def render_markdown(digest: dict, day: str) -> str:
    lines = [f"# Watchlist digest — {day}", ""]
    lines.append(_narrative(digest))
    lines.append("")
    for i in digest.get("items", []):
        t = i.get("ticker", "?")
        if "error" in i:
            lines.append(f"## {t}\n\n_Couldn't load: {i['error']}_\n")
            continue
        lines.append(
            f"## {t} — {i['direction']} {i['move_pct']:+.2f}% over {i['period']} "
            f"({i['movement_label']}, now ${i['current_price']:.2f})"
        )
        if i["headlines"]:
            lines.append("")
            for h in i["headlines"]:
                pub = f" — {h['publisher']}" if h.get("publisher") else ""
                link = f" ({h['url']})" if h.get("url") else ""
                lines.append(f"- {h['title']}{pub}{link}")
        else:
            lines.append("\n_No headlines in this window._")
        lines.append("")
    lines.append("---")
    lines.append("Educational information, not investment advice.")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a daily watchlist digest.")
    parser.add_argument("tickers", nargs="*", help="Tickers (else use the saved watchlist).")
    parser.add_argument("--period", default="1d", help="Move window: 1d, 1w, 1mo, ...")
    parser.add_argument("--out-dir", default=str(config.DATA_DIR / "digests"))
    args = parser.parse_args()

    watchlist = resolve_watchlist(args.tickers)
    print(f"Building digest for {', '.join(watchlist)} (period={args.period})...", file=sys.stderr)

    digest = tools.get_watchlist_digest(watchlist, args.period)
    if "error" in digest:
        print(f"Digest failed: {digest['error']}", file=sys.stderr)
        raise SystemExit(1)

    day = _dt.date.today().isoformat()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"digest-{day}.md"
    out_path.write_text(render_markdown(digest, day), encoding="utf-8")
    print(f"Wrote {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()

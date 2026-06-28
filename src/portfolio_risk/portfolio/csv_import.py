"""CSV transaction import with a MANDATORY dry-run preview.

Brokerages disagree on everything — header names, sign conventions (negative
quantity for sells), "YOU BOUGHT" action strings, ``$``/comma-formatted
prices, MM/DD/YYYY dates. This parser normalizes the common variants
(Fidelity/Schwab-style and minimal exports), reports every unparseable row
instead of failing, and NEVER writes: callers preview ``parse_csv`` output and
then explicitly ``commit_rows``.
"""

from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime

_COL_ALIASES: dict[str, set[str]] = {
    "ticker": {"ticker", "symbol", "stock", "security", "instrument"},
    "side": {"side", "action", "type", "transaction type", "trade type", "activity"},
    "shares": {"shares", "quantity", "qty", "units"},
    "price": {
        "price",
        "share price",
        "price per share",
        "price ($)",
        "unit price",
        "execution price",
        "cost per share",
    },
    "fees": {"fees", "fee", "commission", "commissions", "fees ($)", "commission ($)"},
    "trade_date": {
        "date",
        "trade date",
        "run date",
        "transaction date",
        "activity date",
        "settlement date",
    },
    "note": {"note", "notes", "description", "memo"},
}

_BUY_WORDS = ("buy", "bought", "purchase", "reinvest")
_SELL_WORDS = ("sell", "sold")

_DATE_FORMATS = ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%d-%b-%Y", "%Y/%m/%d")


def _norm_header(h: str) -> str:
    return re.sub(r"\s+", " ", (h or "").strip().lower())


def _map_headers(fieldnames: list[str]) -> dict[str, str]:
    """Map our canonical field -> the CSV's actual header (first alias hit)."""
    normed = {_norm_header(h): h for h in fieldnames}
    mapping: dict[str, str] = {}
    for field, aliases in _COL_ALIASES.items():
        for alias in aliases:
            if alias in normed:
                mapping[field] = normed[alias]
                break
    return mapping


def _clean_number(raw: str) -> float:
    """'$1,234.56' -> 1234.56; '(12)' -> -12 (accounting negatives)."""
    s = (raw or "").strip().replace("$", "").replace(",", "")
    neg = s.startswith("(") and s.endswith(")")
    if neg:
        s = s[1:-1]
    if not s:
        raise ValueError("empty number")
    v = float(s)
    return -v if neg else v


def _parse_date(raw: str) -> str:
    s = (raw or "").strip()
    # "as of" suffixes (Fidelity) and timestamps.
    s = re.split(r"\s+as of\s+", s, flags=re.IGNORECASE)[0].strip()
    s = s.split("T")[0].split(" ")[0]
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"unrecognized date {raw!r}")


def _parse_side(raw: str, shares: float) -> str:
    s = (raw or "").strip().lower()
    if any(w in s for w in _SELL_WORDS):
        return "SELL"
    if any(w in s for w in _BUY_WORDS):
        return "BUY"
    # No action column or unrecognized: fall back to the sign convention
    # (negative quantity = sell).
    return "SELL" if shares < 0 else "BUY"


def parse_csv(text: str) -> dict:
    """Dry-run parse. Returns {"rows": [...], "errors": [...], "columns": {...}}.

    Rows are ready for ``commit_rows``; errors are human-readable, one per bad
    line, and never abort the rest of the file.
    """
    rows: list[dict] = []
    errors: list[str] = []
    try:
        reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
        if not reader.fieldnames:
            return {"rows": [], "errors": ["Empty CSV."], "columns": {}}
        mapping = _map_headers(list(reader.fieldnames))
    except Exception as exc:  # noqa: BLE001
        return {"rows": [], "errors": [f"Could not read CSV: {exc}"], "columns": {}}

    missing = [f for f in ("ticker", "shares", "price") if f not in mapping]
    if missing:
        return {
            "rows": [],
            "errors": [
                f"Missing required column(s): {', '.join(missing)}. "
                f"Recognized headers: {sorted(reader.fieldnames)}"
            ],
            "columns": mapping,
        }

    for lineno, raw in enumerate(reader, start=2):
        try:
            ticker = (raw.get(mapping["ticker"]) or "").strip().upper()
            # Some exports include footer/disclaimer lines — skip silently if
            # the ticker cell is empty or clearly not a symbol.
            if not ticker or not re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,9}", ticker):
                if any((v or "").strip() for v in raw.values()):
                    errors.append(f"Line {lineno}: no valid ticker — skipped.")
                continue
            shares_signed = _clean_number(raw.get(mapping["shares"], ""))
            price = abs(_clean_number(raw.get(mapping["price"], "")))
            side = _parse_side(
                raw.get(mapping.get("side", ""), "") if "side" in mapping else "",
                shares_signed,
            )
            fees = 0.0
            if "fees" in mapping and (raw.get(mapping["fees"]) or "").strip():
                fees = abs(_clean_number(raw[mapping["fees"]]))
            when = (
                _parse_date(raw[mapping["trade_date"]])
                if "trade_date" in mapping and (raw.get(mapping["trade_date"]) or "").strip()
                else date.today().isoformat()
            )
            note = (raw.get(mapping.get("note", ""), "") or "").strip()[:200] if "note" in mapping else ""
            shares = abs(shares_signed)
            if shares == 0:
                errors.append(f"Line {lineno}: zero shares — skipped.")
                continue
            if price == 0:
                errors.append(f"Line {lineno}: zero price — skipped.")
                continue
            rows.append(
                {
                    "ticker": ticker,
                    "side": side,
                    "shares": shares,
                    "price": price,
                    "fees": fees,
                    "trade_date": when,
                    "note": note,
                }
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Line {lineno}: {exc}")

    return {"rows": rows, "errors": errors, "columns": mapping}


def commit_rows(portfolio: str, rows: list[dict]) -> list[dict]:
    """Write previously previewed rows. Separate from parse_csv on purpose —
    imports must always go through an explicit confirm step."""
    from . import store

    return store.add_transactions(portfolio, rows)

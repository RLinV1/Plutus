import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api";
import { Panel } from "../components/terminal/Panel";
import { TickerInput } from "../components/TickerInput";
import { HoldingsTable } from "../components/portfolio/HoldingsTable";
import { DangerReset } from "../components/portfolio/DangerReset";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { fmtSignedPct, fmtUSD } from "../utils";

/** Paper trading: a simulated account that fills market orders at the current
 *  yfinance quote. No real money — a safe place to practice. */
export default function PaperView() {
  const qc = useQueryClient();
  const { data: acct } = useQuery({
    queryKey: ["paper"],
    queryFn: api.paperAccount,
    refetchInterval: 30_000, // live prices move the account value
  });

  const [side, setSide] = useState<"BUY" | "SELL">("BUY");
  const [ticker, setTicker] = useState("");
  const [shares, setShares] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  // Live-ish quote for the ticket so you see roughly what you'll pay.
  const { data: quote } = useQuery({
    queryKey: ["snapshot", ticker],
    queryFn: () => api.snapshot(ticker),
    enabled: /^[A-Z][A-Z0-9.\-]{0,9}$/.test(ticker),
    refetchInterval: 30_000,
  });
  const estPrice = quote && !quote.error ? quote.current_price : null;
  const estValue = estPrice != null && Number(shares) > 0 ? estPrice * Number(shares) : null;

  const heldOptions = (acct?.positions ?? [])
    .filter((h) => h.shares > 0)
    .map((h) => ({ symbol: h.ticker, name: `${h.shares} sh held` }));

  const trade = async () => {
    setBusy(true);
    setMsg("");
    try {
      const res = await api.paperTrade(side, ticker.trim().toUpperCase(), Number(shares));
      if (res.error) {
        setMsg(res.error);
      } else if (res.fill) {
        setMsg(
          `Filled: ${res.fill.side} ${res.fill.shares} ${res.fill.ticker} @ ${fmtUSD(res.fill.price)}`,
        );
        setShares("");
        qc.invalidateQueries({ queryKey: ["paper"] });
      }
    } catch (e) {
      setMsg(String(e));
    } finally {
      setBusy(false);
    }
  };

  const valid = ticker.trim().length > 0 && Number(shares) > 0;

  return (
    <div className="space-y-3">
      {/* Account headline */}
      <div data-tour="paper-account" className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Big label="PAPER CASH" value={fmtUSD(acct?.cash)} />
        <Big label="POSITIONS" value={fmtUSD(acct?.positions_value)} />
        <Big label="TOTAL VALUE" value={fmtUSD(acct?.total_value)} />
        <Big
          label={`RETURN (FROM ${fmtUSD(acct?.start_cash, 0)})`}
          value={acct?.return_pct != null ? `${acct.return_pct >= 0 ? "+" : ""}${acct.return_pct.toFixed(2)}%` : "—"}
          tone={acct ? (acct.return_pct >= 0 ? "up" : "down") : undefined}
        />
      </div>

      <div className="grid grid-cols-1 gap-3 xl:grid-cols-[1fr_minmax(300px,360px)]">
        <div className="min-w-0 space-y-3">
          <Panel title="PAPER POSITIONS">
            {!acct ? (
              <Skeleton className="h-32 w-full" />
            ) : acct.positions.length ? (
              <HoldingsTable
                holdings={acct.positions}
                onSell={(h) => {
                  setSide("SELL");
                  setTicker(h.ticker);
                  setShares(String(h.shares));
                  setMsg("");
                }}
              />
            ) : (
              <p className="text-sm text-muted-foreground">
                No paper positions yet — place your first simulated order on the
                right. You start with {fmtUSD(acct.start_cash, 0)} of pretend money
                and fills use real market prices.
              </p>
            )}
          </Panel>

          <Panel title={`SIMULATED FILLS · ${acct?.n_trades ?? 0}`}>
            {acct?.transactions?.length ? (
              <ul className="chat-scroll max-h-64 space-y-1 overflow-y-auto font-mono text-[0.6875rem]">
                {[...acct.transactions].reverse().map((x) => (
                  <li key={x.id} className="flex items-center gap-2 border-b border-border/40 pb-1">
                    <span className="text-muted-foreground">{x.trade_date}</span>
                    <span className={x.side === "BUY" ? "text-up" : "text-down"}>{x.side}</span>
                    <span className="font-bold">{x.ticker}</span>
                    <span className="tnum">
                      {x.shares} @ {fmtUSD(x.price)}
                    </span>
                    <span className="tnum ml-auto text-muted-foreground">
                      {fmtUSD(x.shares * x.price)}
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-xs text-muted-foreground">No simulated trades yet.</p>
            )}
          </Panel>
        </div>

        <div className="min-w-0 space-y-3">
          <Panel tourId="paper-ticket" title="MARKET ORDER — FILLS AT THE LIVE QUOTE">
            <div className="space-y-2">
              <div className="flex gap-1">
                {(["BUY", "SELL"] as const).map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => setSide(s)}
                    className={cn(
                      "h-8 flex-1 border font-mono text-xs font-bold tracking-widest",
                      side === s
                        ? s === "BUY"
                          ? "border-up bg-up/15 text-up"
                          : "border-down bg-down/15 text-down"
                        : "border-border text-muted-foreground hover:text-foreground",
                    )}
                  >
                    {s}
                  </button>
                ))}
              </div>
              <TickerInput
                value={ticker}
                onChange={setTicker}
                placeholder={side === "SELL" ? "Which position to sell…" : "Ticker or company…"}
                options={side === "SELL" ? heldOptions : undefined}
              />
              <Input
                aria-label="Shares"
                placeholder="Shares"
                type="number"
                min="0"
                step="any"
                value={shares}
                onChange={(e) => setShares(e.target.value)}
                className="font-mono"
              />
              <div className="flex items-baseline justify-between font-mono text-[0.6875rem] text-muted-foreground">
                <span>
                  {estPrice != null ? `last ${fmtUSD(estPrice)}` : "quote loads as you type"}
                </span>
                {estValue != null && (
                  <span>
                    est. {side === "BUY" ? "cost" : "proceeds"}{" "}
                    <span className="font-bold text-foreground">{fmtUSD(estValue)}</span>
                  </span>
                )}
              </div>
              <Button className="w-full" onClick={trade} disabled={!valid || busy}>
                {busy ? "Filling…" : `${side === "BUY" ? "Buy" : "Sell"} at market`}
              </Button>
              {msg && <p className="font-mono text-[0.6875rem] text-muted-foreground">{msg}</p>}
            </div>
          </Panel>

          <Panel title="ABOUT">
            <p className="mb-2 text-xs leading-relaxed text-muted-foreground">
              {acct?.note ??
                "Simulated account — fills use the current market quote; no real money is involved."}
            </p>
            <DangerReset
              requiredText="PAPER"
              buttonLabel="Reset paper account…"
              warning={`This erases all ${acct?.n_trades ?? 0} simulated trade(s) and restores the full ${fmtUSD(acct?.start_cash, 0)} balance. There is no undo.`}
              onConfirm={async () => {
                const res = await api.paperReset();
                qc.invalidateQueries({ queryKey: ["paper"] });
                return `Erased ${res.deleted} trade(s) — back to a fresh account.`;
              }}
            />
          </Panel>
        </div>
      </div>
    </div>
  );
}

function Big({ label, value, tone }: { label: string; value: string; tone?: "up" | "down" }) {
  return (
    <div className="border border-border bg-card px-3 py-2.5">
      <div className="micro">{label}</div>
      <div
        className={cn(
          "tnum mt-1 font-mono text-lg font-bold",
          tone === "up" && "text-up",
          tone === "down" && "text-down",
        )}
      >
        {value}
      </div>
    </div>
  );
}

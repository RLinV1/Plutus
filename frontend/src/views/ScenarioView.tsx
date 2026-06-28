import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import type { ScenarioResult, WhatIfResult } from "../types";
import { Panel } from "../components/terminal/Panel";
import { TickerInput } from "../components/TickerInput";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { PORTFOLIO_TABS, usePortfolio } from "../stores/portfolioStore";
import { fmtUSD } from "../utils";

export default function ScenarioView({ onAsk }: { onAsk: (q: string) => void }) {
  const name = usePortfolio((s) => s.name);
  const setName = usePortfolio((s) => s.setName);

  return (
    <div className="space-y-3">
      {/* What are we stressing: your book or the demo. */}
      <div className="flex flex-wrap items-center gap-1">
        <span className="micro mr-1">RUN AGAINST</span>
        {PORTFOLIO_TABS.map(({ id, label }) => (
          <button
            key={id}
            onClick={() => setName(id)}
            className={cn(
              "border px-3 py-1.5 font-mono text-[0.6875rem] font-bold tracking-wider",
              name === id
                ? "border-primary bg-primary/15 text-primary"
                : "border-border text-muted-foreground hover:text-foreground",
            )}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        <StressTest onAsk={onAsk} portfolio={name} />
        <div className="space-y-3">
          <WhatIf portfolio={name} />
          <Rebalance portfolio={name} />
        </div>
      </div>
    </div>
  );
}

function StressTest({
  onAsk,
  portfolio,
}: {
  onAsk: (q: string) => void;
  portfolio: string;
}) {
  const [selected, setSelected] = useState("covid_2020");
  const { data: catalog = [] } = useQuery({
    queryKey: ["scenarios"],
    queryFn: api.scenarios,
    staleTime: Infinity,
  });
  const { data: result } = useQuery<ScenarioResult>({
    queryKey: ["portfolio", portfolio, "scenario", selected],
    queryFn: () => api.scenario(portfolio, selected),
  });

  return (
    <Panel
      tourId="stress"
      title="STRESS TEST — IF HISTORY REPEATED"
      right={
        <Button
          size="sm"
          variant="ghost"
          onClick={() =>
            onAsk(`How would my portfolio handle a ${selected.replace("_", " ")} style crash?`)
          }
        >
          Explain ↗
        </Button>
      }
    >
      <div className="mb-3 flex flex-wrap gap-1">
        {catalog.map((s) => (
          <button
            key={s.id}
            onClick={() => setSelected(s.id)}
            className={cn(
              "border px-2 py-1 font-mono text-[0.6875rem]",
              selected === s.id
                ? "border-primary bg-primary/15 text-primary"
                : "border-border text-muted-foreground hover:text-foreground",
            )}
            title={`${s.window} · market ${s.market_drop_pct}%`}
          >
            {s.label}
          </button>
        ))}
      </div>

      {!result ? (
        <Skeleton className="h-48 w-full" />
      ) : result.error ? (
        <p className="text-sm text-muted-foreground">{result.error}</p>
      ) : (
        <>
          <div className="flex flex-wrap items-baseline gap-x-6 gap-y-2">
            <div>
              <div className="micro">ESTIMATED IMPACT</div>
              <div className="tnum font-mono text-2xl font-bold text-down">
                {result.estimated_loss_pct.toFixed(1)}% ({fmtUSD(result.estimated_loss, 0)})
              </div>
            </div>
            <div>
              <div className="micro">VALUE AFTER</div>
              <div className="tnum font-mono text-2xl font-bold">
                {fmtUSD(result.estimated_value_after, 0)}
              </div>
            </div>
            {result.vs_daily_var != null && (
              <div>
                <div className="micro">VS TYPICAL BAD DAY</div>
                <div className="tnum font-mono text-2xl font-bold text-primary">
                  ~{result.vs_daily_var.toFixed(0)}×
                </div>
              </div>
            )}
          </div>

          <table className="mt-3 w-full font-mono text-xs">
            <thead>
              <tr className="micro border-b border-border text-left">
                <th className="py-1">TICKER</th>
                <th className="py-1 text-right">VALUE</th>
                <th className="py-1 text-right">BETA</th>
                <th className="py-1 text-right">EST. MOVE</th>
                <th className="py-1 text-right">EST. $</th>
              </tr>
            </thead>
            <tbody>
              {result.positions.map((p) => (
                <tr key={p.ticker} className="border-b border-border/40">
                  <td className="py-1 font-bold">{p.ticker}</td>
                  <td className="tnum py-1 text-right">{fmtUSD(p.market_value, 0)}</td>
                  <td className="tnum py-1 text-right">{p.beta.toFixed(2)}</td>
                  <td className="tnum py-1 text-right text-down">
                    {p.estimated_move_pct.toFixed(1)}%
                  </td>
                  <td className="tnum py-1 text-right text-down">
                    {fmtUSD(p.estimated_change, 0)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-2 text-[0.6875rem] leading-relaxed text-muted-foreground">
            {result.note}
          </p>
        </>
      )}
    </Panel>
  );
}

function WhatIf({ portfolio }: { portfolio: string }) {
  const [side, setSide] = useState<"BUY" | "SELL">("BUY");
  const [ticker, setTicker] = useState("");
  const [shares, setShares] = useState("");
  const [result, setResult] = useState<WhatIfResult | null>(null);
  const [busy, setBusy] = useState(false);

  const run = async () => {
    setBusy(true);
    try {
      setResult(await api.simulate(portfolio, side, ticker.trim().toUpperCase(), Number(shares)));
    } finally {
      setBusy(false);
    }
  };

  const rows: [string, keyof NonNullable<WhatIfResult["before"]>, string][] = [
    ["VOLATILITY /YR", "volatility_annual_pct", "%"],
    ["BETA", "beta", ""],
    ["SHARPE", "sharpe", ""],
    ["DAILY VAR 95", "var_hist_95_pct", "%"],
    ["TOP POSITION", "top_weight_pct", "%"],
  ];

  return (
    <Panel tourId="whatif" title="WHAT-IF TRADE — SANDBOX, NOTHING IS SAVED">
      <div className="flex flex-wrap items-end gap-2">
        <div className="flex gap-1">
          {(["BUY", "SELL"] as const).map((s) => (
            <button
              key={s}
              onClick={() => setSide(s)}
              className={cn(
                "h-9 border px-3 font-mono text-xs font-bold",
                side === s
                  ? s === "BUY"
                    ? "border-up bg-up/15 text-up"
                    : "border-down bg-down/15 text-down"
                  : "border-border text-muted-foreground",
              )}
            >
              {s}
            </button>
          ))}
        </div>
        <Input
          aria-label="Shares"
          placeholder="Shares"
          type="number"
          min="0"
          step="any"
          className="w-24 font-mono"
          value={shares}
          onChange={(e) => setShares(e.target.value)}
        />
        <TickerInput
          value={ticker}
          onChange={setTicker}
          placeholder="Ticker"
          className="w-40"
        />
        <Button onClick={run} disabled={busy || !ticker.trim() || Number(shares) <= 0}>
          {busy ? "Simulating…" : "Simulate"}
        </Button>
      </div>

      {result?.error && <p className="mt-2 text-sm text-down">{result.error}</p>}

      {/* Empty portfolio: there's no "before" to compare — show what the trade
          alone would look like instead of silently rendering nothing. */}
      {result && !result.error && !result.before && (
        <div className="mt-3 space-y-2">
          <p className="text-sm text-foreground/90">
            Starting from an empty portfolio, {result.trade.side.toLowerCase()}ing{" "}
            {result.trade.shares} {result.trade.ticker} (~
            {fmtUSD(result.trade.est_value, 0)}) would give you:
          </p>
          <dl className="grid grid-cols-2 gap-x-4 gap-y-2 font-mono text-xs sm:grid-cols-3">
            {rows.map(([label, key, unit]) => (
              <div key={key}>
                <dt className="micro">{label}</dt>
                <dd className="tnum mt-0.5 font-bold">
                  {result.after[key].toFixed(2)}
                  {unit}
                </dd>
              </div>
            ))}
          </dl>
        </div>
      )}

      {result && !result.error && result.before && (
        <table className="mt-3 w-full font-mono text-xs">
          <thead>
            <tr className="micro border-b border-border text-left">
              <th className="py-1">METRIC</th>
              <th className="py-1 text-right">BEFORE</th>
              <th className="py-1 text-right">AFTER</th>
              <th className="py-1 text-right">Δ</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(([label, key, unit]) => {
              const b = result.before![key];
              const a = result.after[key];
              const d = a - b;
              return (
                <tr key={key} className="border-b border-border/40">
                  <td className="py-1 text-muted-foreground">{label}</td>
                  <td className="tnum py-1 text-right">
                    {b.toFixed(2)}
                    {unit}
                  </td>
                  <td className="tnum py-1 text-right font-bold">
                    {a.toFixed(2)}
                    {unit}
                  </td>
                  <td
                    className={cn(
                      "tnum py-1 text-right",
                      (key === "sharpe" ? d >= 0 : d <= 0) ? "text-up" : "text-down",
                    )}
                  >
                    {d >= 0 ? "+" : ""}
                    {d.toFixed(2)}
                    {unit}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
      {result && !result.error && (
        <p className="mt-2 text-[0.6875rem] text-muted-foreground">
          Metrics are measured over the last ~2 years of daily prices (504
          trading days) with your weights before vs. after the trade — a risk
          comparison, not a forecast. {result.note}
        </p>
      )}
    </Panel>
  );
}

function Rebalance({ portfolio }: { portfolio: string }) {
  const { data } = useQuery({
    queryKey: ["portfolio", portfolio, "rebalance"],
    queryFn: () => api.rebalance(portfolio),
  });

  return (
    <Panel title="REBALANCE — BACK TO EQUAL WEIGHT">
      {!data ? (
        <Skeleton className="h-24 w-full" />
      ) : data.error ? (
        <p className="text-sm text-muted-foreground">{data.error}</p>
      ) : data.suggested_trades.length ? (
        <>
          <ul className="space-y-1 font-mono text-xs">
            {data.suggested_trades.map((t) => (
              <li key={t.ticker} className="flex items-center gap-2">
                <span className={t.action === "BUY" ? "w-10 text-up" : "w-10 text-down"}>
                  {t.action}
                </span>
                <span className="w-14 font-bold">{t.ticker}</span>
                <span className="tnum">{t.shares} sh</span>
                <span className="tnum ml-auto text-muted-foreground">
                  ≈ {fmtUSD(t.est_value, 0)}
                </span>
              </li>
            ))}
          </ul>
          <p className="mt-2 text-[0.6875rem] text-muted-foreground">{data.note}</p>
        </>
      ) : (
        <p className="text-sm text-muted-foreground">
          Already within 0.5% of equal weight — no trades suggested.
        </p>
      )}
    </Panel>
  );
}

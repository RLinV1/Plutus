import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api";
import { Panel } from "../components/terminal/Panel";
import { HoldingsTable } from "../components/portfolio/HoldingsTable";
import {
  TransactionForm,
  type TradePrefill,
} from "../components/portfolio/TransactionForm";
import { DangerReset } from "../components/portfolio/DangerReset";
import { CsvImport } from "../components/portfolio/CsvImport";
import { Modal } from "../components/terminal/Modal";
import { EquityCurveChart } from "../components/charts/EquityCurve";
import { AllocationDonut } from "../components/charts/AllocationDonut";
import { CorrelationHeatmap } from "../components/charts/CorrelationHeatmap";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { PORTFOLIO_TABS, usePortfolio } from "../stores/portfolioStore";
import { fmtSignedPct, fmtUSD } from "../utils";

export default function PortfolioView({ onAsk }: { onAsk: (q: string) => void }) {
  const qc = useQueryClient();
  const PORTFOLIO = usePortfolio((s) => s.name);
  const setPortfolio = usePortfolio((s) => s.setName);
  const [prefill, setPrefill] = useState<TradePrefill | null>(null);
  const [csvOpen, setCsvOpen] = useState(false);

  const { data: ov } = useQuery({
    queryKey: ["portfolio", PORTFOLIO, "overview"],
    queryFn: () => api.portfolio(PORTFOLIO),
  });
  const hasHoldings = !!ov?.holdings?.length;
  const { data: risk } = useQuery({
    queryKey: ["portfolio", PORTFOLIO, "risk"],
    queryFn: () => api.portfolioRisk(PORTFOLIO),
    enabled: hasHoldings,
  });
  const { data: curve } = useQuery({
    queryKey: ["portfolio", PORTFOLIO, "curve"],
    queryFn: () => api.equityCurve(PORTFOLIO),
    enabled: hasHoldings,
  });
  const { data: txns = [] } = useQuery({
    queryKey: ["portfolio", PORTFOLIO, "txns"],
    queryFn: () => api.transactions(PORTFOLIO),
  });

  const t = ov?.totals;

  return (
    <div className="space-y-3">
      {/* Which book are we looking at? Yours, or the bundled sample data. */}
      <div data-tour="ptabs" className="flex items-center gap-1">
        {PORTFOLIO_TABS.map(({ id, label }) => (
          <button
            key={id}
            onClick={() => setPortfolio(id)}
            className={cn(
              "border px-3 py-1.5 font-mono text-[0.6875rem] font-bold tracking-wider",
              PORTFOLIO === id
                ? "border-primary bg-primary/15 text-primary"
                : "border-border text-muted-foreground hover:text-foreground",
            )}
          >
            {label}
          </button>
        ))}
        {PORTFOLIO === "demo" && (
          <span className="ml-2 font-mono text-[0.6875rem] text-muted-foreground">
            sample data for exploring — your own portfolio stays separate
          </span>
        )}
      </div>

      <div className="grid grid-cols-1 gap-3 xl:grid-cols-[1fr_minmax(300px,360px)]">
      {/* Main column */}
      <div className="min-w-0 space-y-3">
        {/* Headline numbers */}
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <Big label="MARKET VALUE" value={fmtUSD(t?.market_value)} />
          <Big
            label="UNREALIZED P&L"
            value={`${fmtUSD(t?.unrealized_pnl)} (${fmtSignedPct(t?.unrealized_pnl_pct)})`}
            tone={t && t.unrealized_pnl >= 0 ? "up" : "down"}
          />
          <Big
            label="REALIZED P&L"
            value={fmtUSD(t?.realized_pnl)}
            tone={t && t.realized_pnl >= 0 ? "up" : "down"}
          />
          <Big
            label="TODAY"
            value={fmtSignedPct(t?.day_change_pct)}
            tone={(t?.day_change_pct ?? 0) >= 0 ? "up" : "down"}
          />
        </div>

        <Panel tourId="holdings" title="HOLDINGS">
          {!ov ? (
            <Skeleton className="h-40 w-full" />
          ) : hasHoldings ? (
            <>
              <HoldingsTable
                holdings={ov.holdings}
                onSell={(h, price) =>
                  setPrefill({
                    side: "SELL",
                    ticker: h.ticker,
                    shares: h.shares,
                    price: Math.round(price * 100) / 100,
                    nonce: Date.now(),
                  })
                }
              />
              {!!ov.warnings?.length && (
                <ul className="mt-2 space-y-0.5 font-mono text-[0.6875rem] text-primary">
                  {ov.warnings.map((w, i) => (
                    <li key={i}>⚠ {w}</li>
                  ))}
                </ul>
              )}
            </>
          ) : (
            <p className="text-sm text-muted-foreground">
              No holdings yet — record your first buy on the right, import a
              brokerage CSV, or open the DEMO tab above to explore with sample
              data.
            </p>
          )}
        </Panel>

        {hasHoldings && (
          <Panel title="EQUITY CURVE — ACCOUNT VALUE OVER TIME">
            {curve?.points?.length ? (
              <>
                <EquityCurveChart points={curve.points} />
                {curve.summary && (
                  <p className="mt-1 font-mono text-[0.6875rem] text-muted-foreground">
                    {curve.summary.start} → {curve.summary.end} · investment return
                    (excluding money you added):{" "}
                    {fmtSignedPct((curve.summary.twr_return_pct ?? 0) / 100)} · worst
                    peak-to-bottom dip: {curve.summary.max_drawdown_pct?.toFixed(1)}%
                  </p>
                )}
              </>
            ) : (
              <Skeleton className="h-[260px] w-full" />
            )}
          </Panel>
        )}

        {hasHoldings && (
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            <Panel title="ALLOCATION">
              <AllocationDonut holdings={ov.holdings} />
              {ov.concentration && (
                <p className="mt-2 border-t border-border pt-2 text-xs text-muted-foreground">
                  <span className="micro mr-1 text-primary">{ov.concentration}</span>
                  {ov.concentration_detail}
                </p>
              )}
            </Panel>
            <Panel title="CORRELATION — DO THEY MOVE TOGETHER?">
              {risk?.correlation ? (
                <>
                  <CorrelationHeatmap
                    tickers={risk.correlation.tickers}
                    matrix={risk.correlation.matrix}
                  />
                  {risk.highest_correlated_pair && (
                    <p className="mt-2 text-xs text-muted-foreground">
                      Most in-sync: {risk.highest_correlated_pair.tickers.join(" & ")} (
                      {risk.highest_correlated_pair.correlation.toFixed(2)}).
                    </p>
                  )}
                </>
              ) : (
                <Skeleton className="h-32 w-full" />
              )}
            </Panel>
          </div>
        )}

        {hasHoldings && (
          <Panel
            title="RISK REPORT"
            right={
              <Button size="sm" variant="ghost" onClick={() => onAsk("How risky is my portfolio?")}>
                Explain ↗
              </Button>
            }
          >
            {risk && !risk.error ? (
              <>
                <dl className="grid grid-cols-2 gap-x-4 gap-y-2 font-mono text-xs sm:grid-cols-4">
                  <Datum k="VOLATILITY /YR" v={`${risk.volatility_annual_pct?.toFixed(1)}%`} />
                  <Datum k="BETA" v={risk.beta?.toFixed(2)} />
                  <Datum k="SHARPE" v={risk.sharpe?.toFixed(2)} />
                  <Datum k="MAX DRAWDOWN" v={`${(risk.max_drawdown * 100).toFixed(1)}%`} />
                  <Datum
                    k="DAILY VAR 95"
                    v={`${(risk.var_hist_95 * 100).toFixed(2)}% ≈ ${fmtUSD(risk.var_hist_95_dollars, 0)}`}
                  />
                  <Datum
                    k="CVAR 95"
                    v={`${(risk.cvar_95 * 100).toFixed(2)}% ≈ ${fmtUSD(risk.cvar_95_dollars, 0)}`}
                  />
                  <Datum k="MC VAR 95" v={`${(risk.var_mc_95 * 100).toFixed(2)}%`} />
                  <Datum k="HHI" v={risk.hhi?.toFixed(2)} />
                </dl>
                <p className="mt-2 border-t border-border pt-2 text-xs text-muted-foreground">
                  {risk.plain_summary}
                </p>
              </>
            ) : (
              <Skeleton className="h-20 w-full" />
            )}
          </Panel>
        )}
      </div>

      {/* Right rail: record trades, import, ledger */}
      <div className="min-w-0 space-y-3">
        <Panel tourId="trade" title="RECORD A TRADE">
          <TransactionForm
            portfolio={PORTFOLIO}
            prefill={prefill}
            holdings={ov?.holdings ?? []}
          />
        </Panel>
        <Panel tourId="import" title="BULK IMPORT">
          <Button
            variant="outline"
            size="sm"
            className="w-full"
            onClick={() => setCsvOpen(true)}
          >
            ⇪ Import brokerage CSV…
          </Button>
        </Panel>
        {csvOpen && (
          <Modal title="IMPORT BROKERAGE CSV" onClose={() => setCsvOpen(false)}>
            <CsvImport portfolio={PORTFOLIO} />
          </Modal>
        )}
        <Panel title={`LEDGER · ${txns.length} TXNS`}>
          {txns.length ? (
            <ul className="chat-scroll max-h-72 space-y-1 overflow-y-auto font-mono text-[0.6875rem]">
              {[...txns].reverse().map((x) => (
                <li key={x.id} className="flex items-center gap-2 border-b border-border/40 pb-1">
                  <span className="text-muted-foreground">{x.trade_date}</span>
                  <span className={x.side === "BUY" ? "text-up" : "text-down"}>{x.side}</span>
                  <span className="font-bold">{x.ticker}</span>
                  <span className="tnum">
                    {x.shares} @ {fmtUSD(x.price)}
                  </span>
                  <button
                    aria-label={`Delete transaction ${x.id}`}
                    className="ml-auto text-muted-foreground hover:text-down"
                    onClick={async () => {
                      await api.deleteTransaction(x.id);
                      qc.invalidateQueries({ queryKey: ["portfolio"] });
                    }}
                  >
                    ×
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-xs text-muted-foreground">No transactions recorded yet.</p>
          )}
        </Panel>
        <Panel title="AI BRIEFING">
          <Button className="w-full" variant="outline" onClick={() => onAsk("Give me my portfolio briefing for today")}>
            ✦ What changed today — and why?
          </Button>
        </Panel>
        <Panel tourId="danger" title="DANGER ZONE">
          <DangerReset
            requiredText={PORTFOLIO}
            buttonLabel={`Reset ${PORTFOLIO.toUpperCase()} portfolio…`}
            warning={`This permanently deletes all ${txns.length} transaction(s) in ${PORTFOLIO.toUpperCase()} — holdings, cost basis, and P&L history. There is no undo.`}
            onConfirm={async (typed) => {
              const res = await api.resetPortfolio(PORTFOLIO, typed);
              if (res.error) throw new Error(res.error);
              qc.invalidateQueries({ queryKey: ["portfolio"] });
              return `Deleted ${res.deleted} transaction(s) — portfolio is empty.`;
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

function Datum({ k, v }: { k: string; v?: string }) {
  return (
    <div>
      <dt className="micro">{k}</dt>
      <dd className="tnum mt-0.5">{v ?? "—"}</dd>
    </div>
  );
}

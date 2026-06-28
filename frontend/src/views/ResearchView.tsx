import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import type { BarInterval, Period } from "../types";
import { Panel } from "../components/terminal/Panel";
import { CandleChart } from "../components/charts/CandleChart";
import { useWorkspace } from "../stores/workspace";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { fmtNum, fmtSignedPct, fmtUSD, titleCase } from "../utils";

const PERIODS: Period[] = ["1d", "1w", "1mo", "6mo", "1y", "5y", "max"];
const PERIOD_LABEL: Record<Period, string> = {
  "1d": "1D",
  "1w": "1W",
  "1mo": "1M",
  "6mo": "6M",
  "1y": "1Y",
  "5y": "5Y",
  max: "ALL",
};
// Candle width choices for the intraday periods; 1H is the default.
const INTERVALS: BarInterval[] = ["1m", "10m", "1h"];
const INTERVAL_LABEL: Record<BarInterval, string> = { "1m": "1m", "10m": "10m", "1h": "1H" };

export default function ResearchView() {
  const ticker = useWorkspace((s) => s.ticker);
  const [period, setPeriod] = useState<Period>("1y");
  const [bar, setBar] = useState<BarInterval>("1h");
  const intraday = period === "1d" || period === "1w";

  const { data: snap } = useQuery({
    queryKey: ["snapshot", ticker],
    queryFn: () => api.snapshot(ticker),
  });
  const { data: tech } = useQuery({
    queryKey: ["technicals", ticker],
    queryFn: () => api.technicals(ticker),
  });
  const { data: risk } = useQuery({
    queryKey: ["risk", ticker],
    queryFn: () => api.risk(ticker),
  });
  const { data: ohlc } = useQuery({
    queryKey: ["ohlc", ticker, period, intraday ? bar : "1d"],
    queryFn: () => api.ohlc(ticker, period, intraday ? bar : "1d"),
    refetchInterval: intraday ? 60_000 : false,
  });
  const { data: news } = useQuery({
    queryKey: ["news", ticker],
    queryFn: () => api.news(ticker),
  });
  const { data: intel } = useQuery({
    queryKey: ["intel", ticker],
    queryFn: () => api.intel(ticker),
    staleTime: 6 * 60 * 60 * 1000,
  });
  const { data: fund } = useQuery({
    queryKey: ["fundamentals", ticker],
    queryFn: () => api.fundamentals(ticker),
    staleTime: 24 * 60 * 60 * 1000,
  });
  const { data: div } = useQuery({
    queryKey: ["dividends", ticker],
    queryFn: () => api.dividends(ticker),
    staleTime: 24 * 60 * 60 * 1000,
  });

  const up = (snap?.change_pct ?? 0) >= 0;

  return (
    <div className="space-y-3">
      {snap?.error ? (
        <Panel title="ERROR">
          <p className="text-sm text-down">
            Couldn't load {ticker}: {snap.error}
          </p>
        </Panel>
      ) : (
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-[minmax(280px,340px)_1fr]">
          {/* Left rail: identity + profile. Flex so PROFILE stretches to the
              bottom of the row — no dead space under the rail. */}
          <div className="flex flex-col gap-3">
            <Panel tourId="quote" title={`QUOTE · ${ticker}`}>
              {snap ? (
                <>
                  <div className="text-sm font-semibold">{snap.name}</div>
                  <div className="text-xs text-muted-foreground">
                    {[snap.sector, snap.industry].filter(Boolean).join(" · ")}
                  </div>
                  <div className="tnum mt-2 font-mono text-3xl font-bold">
                    {fmtUSD(snap.current_price)}
                  </div>
                  <div className={cn("tnum font-mono text-sm", up ? "text-up" : "text-down")}>
                    {up ? "▲" : "▼"} {fmtSignedPct(snap.change_pct)} today
                  </div>
                  <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-2 font-mono text-xs">
                    <Datum k="MKT CAP" v={snap.market_cap_human} />
                    <Datum k="P/E" v={fmtNum(snap.pe_ratio)} />
                    <Datum k="VOL PROFILE" v={titleCase(snap.movement)} />
                    <Datum k="RSI 14D" v={fmtNum(tech?.rsi, 0)} />
                    <Datum k="SMA 50" v={fmtUSD(tech?.sma_50)} />
                    <Datum k="SMA 200" v={fmtUSD(tech?.sma_200)} />
                    <Datum
                      k="52W RANGE"
                      v={
                        tech?.low_52w != null
                          ? `${fmtUSD(tech.low_52w, 0)}–${fmtUSD(tech.high_52w, 0)}`
                          : "—"
                      }
                    />
                    <Datum k="BETA" v={fmtNum(risk?.beta)} />
                    <Datum
                      k="DIV YIELD"
                      v={
                        snap.dividend_yield != null && snap.dividend_yield > 0
                          ? `${(snap.dividend_yield * 100).toFixed(2)}%`
                          : "—"
                      }
                    />
                    <Datum k="FWD P/E" v={fmtNum(snap.forward_pe)} />
                    <Datum
                      k="PROFIT MARGIN"
                      v={
                        snap.profit_margin != null
                          ? `${(snap.profit_margin * 100).toFixed(1)}%`
                          : "—"
                      }
                    />
                    <Datum
                      k="REV GROWTH"
                      v={
                        snap.revenue_growth != null
                          ? `${snap.revenue_growth >= 0 ? "+" : ""}${(snap.revenue_growth * 100).toFixed(1)}%`
                          : "—"
                      }
                    />
                  </dl>
                  {(snap.recommendation || snap.analyst_target != null) && (
                    <p className="mt-2 border-t border-border pt-2 font-mono text-xs text-muted-foreground">
                      <span className="micro mr-1">ANALYSTS</span>
                      {snap.recommendation && (
                        <span className="font-bold text-foreground">
                          {snap.recommendation.replace(/_/g, " ").toUpperCase()}
                        </span>
                      )}
                      {snap.analyst_target != null && (
                        <> · target {fmtUSD(snap.analyst_target)}</>
                      )}
                      {snap.analyst_count != null && <> · {snap.analyst_count} analysts</>}
                    </p>
                  )}
                </>
              ) : (
                <div className="space-y-2">
                  <Skeleton className="h-5 w-40" />
                  <Skeleton className="h-9 w-32" />
                  <Skeleton className="h-24 w-full" />
                </div>
              )}
            </Panel>

            <Panel title="PROFILE" className="flex-1">
              <p className="text-[0.8125rem] leading-relaxed text-foreground/85">
                {snap?.description ?? "…"}
              </p>
              {snap && (
                <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-2 border-t border-border pt-3 font-mono text-xs">
                  <Datum k="SECTOR" v={snap.sector ?? "—"} />
                  <Datum k="INDUSTRY" v={snap.industry ?? "—"} />
                  <Datum k="COUNTRY" v={snap.country ?? "—"} />
                  <Datum
                    k="EMPLOYEES"
                    v={snap.employees != null ? snap.employees.toLocaleString() : "—"}
                  />
                  <Datum
                    k="NEXT EARNINGS"
                    v={intel?.next_earnings ?? "—"}
                  />
                  <Datum
                    k="EX-DIV DATE"
                    v={intel?.ex_dividend_date ?? "—"}
                  />
                </dl>
              )}
              {snap?.website && (
                <p className="mt-2 font-mono text-[0.6875rem] text-muted-foreground">
                  <a
                    href={snap.website}
                    target="_blank"
                    rel="noreferrer"
                    className="text-info hover:underline"
                  >
                    {snap.website.replace(/^https?:\/\/(www\.)?/, "")}
                  </a>
                </p>
              )}
              {risk && (
                <p className="mt-2 border-t border-border pt-2 text-xs leading-relaxed text-muted-foreground">
                  {risk.plain_summary}
                </p>
              )}
              {fund && !fund.error && (
                <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">
                  {fund.plain_summary}
                </p>
              )}
            </Panel>

          </div>

          {/* Main: candles + news */}
          <div className="space-y-3">
            <Panel
              tourId="chart"
              title={`PRICE · ${ticker} · ${intraday ? INTERVAL_LABEL[bar].toUpperCase() + " BARS" : "DAILY"}`}
              right={
                <div className="flex items-center gap-0.5">
                  {intraday && (
                    <>
                      {INTERVALS.map((iv) => (
                        <button
                          key={iv}
                          onClick={() => setBar(iv)}
                          className={cn(
                            "px-2 py-0.5 font-mono text-[0.625rem] font-bold",
                            bar === iv
                              ? "bg-info/80 text-primary-foreground"
                              : "text-muted-foreground hover:text-foreground",
                          )}
                        >
                          {INTERVAL_LABEL[iv]}
                        </button>
                      ))}
                      <span className="mx-1 h-3 w-px bg-border" />
                    </>
                  )}
                  {PERIODS.map((p) => (
                    <button
                      key={p}
                      onClick={() => setPeriod(p)}
                      className={cn(
                        "px-2 py-0.5 font-mono text-[0.625rem] font-bold",
                        period === p
                          ? "bg-primary text-primary-foreground"
                          : "text-muted-foreground hover:text-foreground",
                      )}
                    >
                      {PERIOD_LABEL[p]}
                    </button>
                  ))}
                </div>
              }
            >
              {ohlc?.points?.length ? (
                <CandleChart points={ohlc.points} />
              ) : (
                <Skeleton className="h-[360px] w-full" />
              )}
              {tech && (
                <p className="mt-2 text-xs text-muted-foreground">
                  <span className="micro mr-1">TREND</span> {tech.trend}.
                </p>
              )}
            </Panel>

            <Panel tourId="news" title={`HEADLINES · ${ticker}`}>
              {!news ? (
                <div className="space-y-2">
                  {[0, 1, 2].map((i) => (
                    <Skeleton key={i} className="h-5 w-full" />
                  ))}
                </div>
              ) : news.articles?.length ? (
                <ul className="space-y-1.5">
                  {news.articles.slice(0, 8).map((a, i) => (
                    <li key={i} className="flex items-baseline gap-2 text-[0.8125rem]">
                      <span className="micro shrink-0">
                        {a.published ? a.published.slice(5, 10) : "—"}
                      </span>
                      {a.url ? (
                        <a
                          href={a.url}
                          target="_blank"
                          rel="noreferrer"
                          className="leading-snug hover:text-primary hover:underline"
                        >
                          {a.title}
                        </a>
                      ) : (
                        <span className="leading-snug">{a.title}</span>
                      )}
                      {a.publisher && (
                        <span className="ml-auto hidden shrink-0 font-mono text-[0.625rem] text-muted-foreground sm:inline">
                          {a.publisher}
                        </span>
                      )}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-xs text-muted-foreground">No recent news found.</p>
              )}
            </Panel>

            <Panel title={`INTEL · ${ticker} — EARNINGS, ANALYSTS, INSIDERS, HOLDERS`}>
              {!intel ? (
                <Skeleton className="h-32 w-full" />
              ) : (
                <div className="grid grid-cols-1 gap-x-6 gap-y-4 md:grid-cols-2">
                  <div>
                    <div className="micro mb-1.5 text-primary">NEXT EARNINGS</div>
                    <p className="font-mono text-sm">
                      {intel.next_earnings ? (
                        <>
                          {intel.next_earnings}
                          <span className="ml-2 text-xs text-muted-foreground">
                            (prices often move sharply around earnings)
                          </span>
                        </>
                      ) : (
                        <span className="text-muted-foreground">no date announced</span>
                      )}
                    </p>
                    {intel.ex_dividend_date && (
                      <p className="mt-1 font-mono text-xs text-muted-foreground">
                        ex-dividend: {intel.ex_dividend_date}
                        <span className="ml-1">(own it before this date to get the next payout)</span>
                      </p>
                    )}

                    <div className="micro mb-1.5 mt-4 text-primary">
                      ANALYST RATING CHANGES
                    </div>
                    {intel.upgrades.length ? (
                      <ul className="space-y-1 font-mono text-xs">
                        {intel.upgrades.slice(0, 5).map((u, i) => (
                          <li key={i} className="flex items-baseline gap-2">
                            <span className="shrink-0 text-muted-foreground">{u.date}</span>
                            <span className="truncate">{u.firm}</span>
                            <span
                              className={cn(
                                "ml-auto shrink-0",
                                u.action === "up"
                                  ? "text-up"
                                  : u.action === "down"
                                    ? "text-down"
                                    : "text-muted-foreground",
                              )}
                            >
                              {u.from_grade ? `${u.from_grade} → ` : ""}
                              {u.to_grade}
                            </span>
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="text-xs text-muted-foreground">No recent rating changes.</p>
                    )}
                  </div>

                  <div>
                    <div className="micro mb-1.5 text-primary">INSIDER ACTIVITY</div>
                    {intel.insiders.length ? (
                      <ul className="space-y-1 font-mono text-xs">
                        {intel.insiders.slice(0, 5).map((x, i) => (
                          <li key={i} className="flex items-baseline gap-2">
                            <span className="shrink-0 text-muted-foreground">{x.date}</span>
                            <span className="truncate" title={x.position}>
                              {x.insider}
                            </span>
                            <span
                              className={cn(
                                "ml-auto shrink-0",
                                /buy|purchase/i.test(x.transaction)
                                  ? "text-up"
                                  : /sale|sell/i.test(x.transaction)
                                    ? "text-down"
                                    : "text-muted-foreground", // gifts, exercises, etc.
                              )}
                            >
                              {/gift/i.test(x.transaction) ? "Stock Gift" : x.transaction || "trade"}
                              {x.value != null && x.value > 0 && ` ${fmtUSD(x.value, 0)}`}
                            </span>
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="text-xs text-muted-foreground">No recent insider trades.</p>
                    )}

                    <div className="micro mb-1.5 mt-4 text-primary">TOP INSTITUTIONAL HOLDERS</div>
                    {intel.institutional.length ? (
                      <ul className="space-y-1 font-mono text-xs">
                        {intel.institutional.map((hld, i) => (
                          <li key={i} className="flex items-baseline gap-2">
                            <span className="truncate">{hld.holder}</span>
                            <span className="tnum ml-auto shrink-0 text-muted-foreground">
                              {hld.pct_held != null
                                ? `${(hld.pct_held * 100).toFixed(2)}%`
                                : "—"}
                            </span>
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="text-xs text-muted-foreground">No holder data.</p>
                    )}
                  </div>
                </div>
              )}
            </Panel>

            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              <Panel title={`FUNDAMENTALS · ${ticker}${fund?.period ? ` · ${fund.period}` : ""}`}>
                {!fund ? (
                  <Skeleton className="h-24 w-full" />
                ) : fund.error ? (
                  <p className="text-xs text-muted-foreground">unavailable</p>
                ) : (
                  <>
                    <dl className="grid grid-cols-2 gap-x-3 gap-y-2 font-mono text-xs sm:grid-cols-3">
                      <Datum k="REVENUE" v={fund.revenue_human ?? "—"} />
                      <Datum
                        k="REV GROWTH"
                        v={
                          fund.revenue_growth != null
                            ? `${fund.revenue_growth >= 0 ? "+" : ""}${(fund.revenue_growth * 100).toFixed(1)}%`
                            : "—"
                        }
                      />
                      <Datum k="NET INCOME" v={fund.net_income_human ?? "—"} />
                      <Datum
                        k="GROSS MARGIN"
                        v={fund.gross_margin != null ? `${(fund.gross_margin * 100).toFixed(1)}%` : "—"}
                      />
                      <Datum k="FREE CASH FLOW" v={fund.free_cash_flow_human ?? "—"} />
                      <Datum
                        k="DEBT/EQUITY"
                        v={fund.debt_to_equity != null ? fund.debt_to_equity.toFixed(2) : "—"}
                      />
                    </dl>
                    <p className="mt-2 border-t border-border pt-2 text-xs text-muted-foreground">
                      {fund.growth_reading !== "unknown" && `Revenue ${fund.growth_reading}; `}
                      {fund.margin_reading !== "unknown" && `${fund.margin_reading}; `}
                      {fund.debt_reading !== "unknown" && fund.debt_reading}.
                    </p>
                  </>
                )}
              </Panel>

              <Panel title={`DIVIDENDS · ${ticker}`}>
                {!div ? (
                  <Skeleton className="h-16 w-full" />
                ) : div.error ? (
                  <p className="text-xs text-muted-foreground">unavailable</p>
                ) : !div.pays_dividend ? (
                  <p className="text-xs text-muted-foreground">
                    {ticker} doesn't currently pay a dividend.
                  </p>
                ) : (
                  <>
                    <dl className="grid grid-cols-2 gap-x-3 gap-y-2 font-mono text-xs">
                      <Datum k="YIELD" v={`${div.dividend_yield_pct.toFixed(2)}%`} />
                      <Datum k="TTM / SHARE" v={fmtUSD(div.ttm_dividend)} />
                      {div.ex_dividend_date && <Datum k="EX-DIV DATE" v={div.ex_dividend_date} />}
                      {div.recent[0] && (
                        <Datum
                          k="LAST PAYMENT"
                          v={`${fmtUSD(div.recent[0].amount)} · ${div.recent[0].date}`}
                        />
                      )}
                    </dl>
                    <p className="mt-2 border-t border-border pt-2 text-xs leading-relaxed text-muted-foreground">
                      {div.plain_summary}
                    </p>
                  </>
                )}
              </Panel>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function Datum({ k, v }: { k: string; v: string }) {
  return (
    <div>
      <dt className="micro">{k}</dt>
      <dd className="tnum mt-0.5">{v}</dd>
    </div>
  );
}

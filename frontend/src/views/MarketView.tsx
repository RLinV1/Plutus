import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import type { MoverCategory } from "../types";
import { Panel } from "../components/terminal/Panel";
import { useWorkspace } from "../stores/workspace";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { fmtNum, fmtSignedPct, fmtUSD } from "../utils";

const CATEGORIES: { key: MoverCategory; label: string }[] = [
  { key: "gainers", label: "GAINERS" },
  { key: "losers", label: "LOSERS" },
  { key: "active", label: "MOST ACTIVE" },
];

const MOOD_COLOR: Record<string, string> = {
  calm: "text-up",
  normal: "text-foreground",
  nervous: "text-primary",
  fearful: "text-down",
};

export default function MarketView() {
  const openTicker = useWorkspace((s) => s.openTicker);
  const [category, setCategory] = useState<MoverCategory>("gainers");

  const { data: market } = useQuery({
    queryKey: ["market"],
    queryFn: api.market,
    refetchInterval: 60_000,
  });
  const { data: movers } = useQuery({
    queryKey: ["movers", category],
    queryFn: () => api.movers(category),
    refetchInterval: 5 * 60_000,
  });

  return (
    <div className="space-y-3">
      {/* Index strip */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5">
        {market?.indices?.length
          ? market.indices.map((ix) => {
              const up = ix.change_pct >= 0;
              return (
                <Panel key={ix.symbol} title={ix.name.toUpperCase()}>
                  <div className="tnum font-mono text-2xl font-bold">
                    {ix.level.toLocaleString("en-US", { maximumFractionDigits: 2 })}
                  </div>
                  <div className={cn("tnum font-mono text-sm", up ? "text-up" : "text-down")}>
                    {up ? "▲" : "▼"} {fmtSignedPct(ix.change_pct)} today
                  </div>
                </Panel>
              );
            })
          : [0, 1, 2].map((i) => (
              <Panel key={i} title="…">
                <Skeleton className="h-12 w-full" />
              </Panel>
            ))}
        <Panel title="VIX · FEAR GAUGE">
          {market ? (
            market.vix ? (
              <>
                <div className="tnum font-mono text-2xl font-bold">
                  {fmtNum(market.vix.level, 2)}
                </div>
                <div
                  className={cn(
                    "font-mono text-sm font-bold uppercase",
                    MOOD_COLOR[market.mood] ?? "text-foreground",
                  )}
                >
                  {market.mood}
                </div>
              </>
            ) : (
              <p className="text-xs text-muted-foreground">unavailable</p>
            )
          ) : (
            <Skeleton className="h-12 w-full" />
          )}
        </Panel>
        <Panel title="10-YEAR TREASURY">
          {market ? (
            <>
              <div className="tnum font-mono text-2xl font-bold">
                {market.ten_year_yield_pct != null
                  ? `${fmtNum(market.ten_year_yield_pct, 2)}%`
                  : "—"}
              </div>
              <div className="font-mono text-xs text-muted-foreground">yield</div>
            </>
          ) : (
            <Skeleton className="h-12 w-full" />
          )}
        </Panel>
      </div>

      {market?.plain_summary && (
        <Panel title="READ">
          <p className="text-[0.8125rem] leading-relaxed text-foreground/85">
            {market.plain_summary}
          </p>
          <p className="mt-1.5 text-[0.6875rem] text-muted-foreground">
            The VIX measures how much movement option traders expect over the next
            30 days — higher means more fear. This is educational information, not
            investment advice.
          </p>
        </Panel>
      )}

      {/* Movers */}
      <Panel
        title="TODAY'S MOVERS"
        right={
          <div className="flex gap-0.5">
            {CATEGORIES.map((c) => (
              <button
                key={c.key}
                onClick={() => setCategory(c.key)}
                className={cn(
                  "px-2 py-0.5 font-mono text-[0.625rem] font-bold",
                  category === c.key
                    ? "bg-primary text-primary-foreground"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                {c.label}
              </button>
            ))}
          </div>
        }
      >
        {!movers ? (
          <div className="space-y-2">
            {[0, 1, 2, 3, 4].map((i) => (
              <Skeleton key={i} className="h-6 w-full" />
            ))}
          </div>
        ) : movers.rows.length ? (
          <table className="w-full font-mono text-xs">
            <thead>
              <tr className="micro text-left">
                <th className="pb-1.5">TICKER</th>
                <th className="pb-1.5">NAME</th>
                <th className="pb-1.5 text-right">PRICE</th>
                <th className="pb-1.5 text-right">TODAY</th>
                <th className="hidden pb-1.5 text-right sm:table-cell">VOLUME</th>
              </tr>
            </thead>
            <tbody>
              {movers.rows.map((r) => {
                const up = (r.change_pct ?? 0) >= 0;
                return (
                  <tr
                    key={r.ticker}
                    onClick={() => openTicker(r.ticker)}
                    className="cursor-pointer border-t border-border/60 hover:bg-primary/10"
                    title={`Open ${r.ticker} in RESEARCH`}
                  >
                    <td className="py-1.5 font-bold text-primary">{r.ticker}</td>
                    <td className="max-w-[18rem] truncate py-1.5 text-foreground/85">
                      {r.name}
                    </td>
                    <td className="tnum py-1.5 text-right">{fmtUSD(r.price)}</td>
                    <td
                      className={cn(
                        "tnum py-1.5 text-right",
                        up ? "text-up" : "text-down",
                      )}
                    >
                      {fmtSignedPct(r.change_pct)}
                    </td>
                    <td className="tnum hidden py-1.5 text-right text-muted-foreground sm:table-cell">
                      {r.volume != null
                        ? r.volume >= 1e6
                          ? `${(r.volume / 1e6).toFixed(1)}M`
                          : r.volume.toLocaleString()
                        : "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        ) : (
          <p className="text-xs text-muted-foreground">
            {movers.note ?? "No mover data right now."}
          </p>
        )}
        <p className="mt-2 text-[0.6875rem] text-muted-foreground">
          Click a row to open it in RESEARCH. Source: Yahoo Finance screeners
          (free, ~5&nbsp;min refresh).
        </p>
      </Panel>
    </div>
  );
}

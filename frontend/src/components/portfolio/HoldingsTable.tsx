import type { Holding } from "../../types";
import { useStream } from "../../stores/streamStore";
import { useWorkspace } from "../../stores/workspace";
import { cn } from "@/lib/utils";
import { fmtSignedPct, fmtUSD } from "../../utils";

/** Dense holdings grid. Live quotes from the stream override the snapshot
 *  price; green/red appears ONLY on P&L and day-change numbers. ``onSell``
 *  adds a quick-SELL button per row that preloads the trade form. */
export function HoldingsTable({
  holdings,
  onSell,
}: {
  holdings: Holding[];
  onSell?: (h: Holding, price: number) => void;
}) {
  const quotes = useStream((s) => s.quotes);
  const lastTick = useStream((s) => s.lastTick);
  const openTicker = useWorkspace((s) => s.openTicker);

  return (
    <div className="overflow-x-auto">
      <table className="w-full font-mono text-xs">
        <thead>
          <tr className="micro border-b border-border text-left">
            <th className="py-1.5 pr-2">TICKER</th>
            <th className="py-1.5 pr-2 text-right">SHARES</th>
            <th className="py-1.5 pr-2 text-right">AVG COST</th>
            <th className="py-1.5 pr-2 text-right">PRICE</th>
            <th className="py-1.5 pr-2 text-right">DAY</th>
            <th className="py-1.5 pr-2 text-right">VALUE</th>
            <th className="py-1.5 pr-2 text-right">WEIGHT</th>
            <th className="py-1.5 text-right">P&amp;L</th>
            {onSell && <th className="py-1.5 pl-2" aria-label="Actions" />}
          </tr>
        </thead>
        <tbody>
          {holdings.map((h) => {
            const live = quotes[h.ticker];
            const price = live?.price ?? h.price;
            const day = live?.change_pct ?? h.day_change_pct;
            const value = h.shares * price;
            const pnl = value - h.cost_basis;
            const pnlPct = h.cost_basis > 0 ? value / h.cost_basis - 1 : null;
            return (
              <tr key={h.ticker} className="border-b border-border/50 hover:bg-accent/40">
                <td className="py-1.5 pr-2">
                  <button
                    className="font-bold text-foreground hover:text-primary"
                    onClick={() => openTicker(h.ticker)}
                    title={h.name}
                  >
                    {h.ticker}
                  </button>
                </td>
                <td className="tnum py-1.5 pr-2 text-right">{h.shares}</td>
                <td className="tnum py-1.5 pr-2 text-right text-muted-foreground">
                  {fmtUSD(h.avg_cost)}
                </td>
                <td
                  className={cn(
                    "tnum py-1.5 pr-2 text-right",
                    lastTick[h.ticker] === "up" && "flash-up",
                    lastTick[h.ticker] === "down" && "flash-down",
                  )}
                >
                  {fmtUSD(price)}
                </td>
                <td
                  className={cn(
                    "tnum py-1.5 pr-2 text-right",
                    (day ?? 0) >= 0 ? "text-up" : "text-down",
                  )}
                >
                  {fmtSignedPct(day)}
                </td>
                <td className="tnum py-1.5 pr-2 text-right">{fmtUSD(value)}</td>
                <td className="tnum py-1.5 pr-2 text-right text-muted-foreground">
                  {h.weight != null ? `${(h.weight * 100).toFixed(1)}%` : "—"}
                </td>
                <td
                  className={cn(
                    "tnum py-1.5 text-right font-bold",
                    pnl >= 0 ? "text-up" : "text-down",
                  )}
                >
                  {fmtUSD(pnl)}
                  <span className="ml-1 font-normal">({fmtSignedPct(pnlPct)})</span>
                </td>
                {onSell && (
                  <td className="py-1.5 pl-2 text-right">
                    <button
                      onClick={() => onSell(h, price)}
                      className="border border-down/50 px-2 py-0.5 font-mono text-[0.625rem] font-bold text-down hover:bg-down/15"
                      title={`Sell ${h.ticker} — preloads the trade form with all ${h.shares} shares at the current price`}
                    >
                      SELL
                    </button>
                  </td>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

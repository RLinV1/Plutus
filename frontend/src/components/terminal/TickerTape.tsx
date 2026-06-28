import { Fragment } from "react";
import { useStream } from "../../stores/streamStore";
import { useWorkspace } from "../../stores/workspace";
import { cn } from "@/lib/utils";
import { fmtSignedPct, fmtUSD } from "../../utils";

/** Scrolling tape of live quotes (market staples + held tickers + alert
 *  tickers, fed by the WebSocket). The track renders the sequence enough
 *  times that two identical halves always overflow the viewport, then
 *  animates -50% — a seamless wrap-around with no gap. Hover pauses;
 *  reduced-motion disables the scroll. */
export function TickerTape() {
  const quotes = useStream((s) => s.quotes);
  const quotedAt = useStream((s) => s.quotedAt);
  const lastTick = useStream((s) => s.lastTick);
  const openTicker = useWorkspace((s) => s.openTicker);
  const entries = Object.entries(quotes);

  if (!entries.length) {
    return (
      <div className="flex h-8 items-center border-b border-border bg-card px-3 font-mono text-[0.6875rem] text-muted-foreground">
        TAPE — connecting to the quote stream…
      </div>
    );
  }

  // Each half must comfortably exceed any viewport width: repeat the sequence
  // until a half carries at least ~24 cells.
  const perHalf = Math.max(1, Math.ceil(24 / entries.length));
  const half = (copy: number) => (
    <Fragment key={copy}>
      {Array.from({ length: perHalf }, (_, rep) =>
        entries.map(([t, q]) => {
          const up = (q.change_pct ?? 0) >= 0;
          const primary = copy === 0 && rep === 0;
          return (
            <button
              key={`${copy}-${rep}-${t}`}
              onClick={() => openTicker(t)}
              tabIndex={primary ? 0 : -1}
              aria-hidden={primary ? undefined : true}
              className={cn(
                "mx-3 inline-flex items-baseline gap-2 font-mono text-[0.75rem]",
                lastTick[t] === "up" && "flash-up",
                lastTick[t] === "down" && "flash-down",
              )}
              title={`${t} ${fmtUSD(q.price)} (${fmtSignedPct(q.change_pct)})${
                quotedAt[t] ? ` as of ${quotedAt[t]}` : ""
              } — click to open`}
            >
              <span className="font-bold text-foreground">{t}</span>
              <span className="tnum text-muted-foreground">{fmtUSD(q.price)}</span>
              <span className={cn("tnum", up ? "text-up" : "text-down")}>
                {up ? "▲" : "▼"} {fmtSignedPct(q.change_pct)}
              </span>
            </button>
          );
        }),
      )}
    </Fragment>
  );

  // Slower with more content so the read speed stays constant.
  const duration = Math.max(40, entries.length * perHalf * 3);

  return (
    <div data-tour="tape" className="h-8 overflow-hidden border-b border-border bg-card">
      <div className="tape-track h-8 items-center" style={{ animationDuration: `${duration}s` }}>
        {half(0)}
        {half(1)}
      </div>
    </div>
  );
}

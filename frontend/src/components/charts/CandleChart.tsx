import { useEffect, useRef, useState } from "react";
import {
  CandlestickSeries,
  ColorType,
  HistogramSeries,
  LineSeries,
  TickMarkType,
  createChart,
  type Time,
} from "lightweight-charts";
import type { OhlcPoint } from "../../types";
import { cn } from "@/lib/utils";

function fmtVol(v: number): string {
  if (v >= 1e9) return `${(v / 1e9).toFixed(1)}B`;
  if (v >= 1e6) return `${(v / 1e6).toFixed(1)}M`;
  if (v >= 1e3) return `${(v / 1e3).toFixed(0)}K`;
  return String(Math.round(v));
}

/** Daily candles carry "YYYY-MM-DD" strings; intraday carry epoch seconds,
 *  rendered in the computer's local timezone. */
function fmtTime(t: string | number): string {
  if (typeof t !== "number") return t;
  return new Date(t * 1000).toLocaleString(undefined, {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

const UP = "#3fae6a";
const DOWN = "#e5484d";
const AMBER = "#ffae0a";
const CYAN = "#39c5e0";

function smaLine(points: OhlcPoint[], window: number) {
  const out: { time: Time; value: number }[] = [];
  let sum = 0;
  for (let i = 0; i < points.length; i++) {
    sum += points[i].c;
    if (i >= window) sum -= points[i - window].c;
    if (i >= window - 1) out.push({ time: points[i].t as Time, value: sum / window });
  }
  return out;
}

/** Canvas candlesticks + volume + 50/200-day SMA overlays (TradingView's
 *  lightweight-charts). SVG can't keep up with 800-point OHLC; canvas can. */
export function CandleChart({ points, height = 360 }: { points: OhlcPoint[]; height?: number }) {
  const ref = useRef<HTMLDivElement>(null);
  // The candle under the cursor (defaults to the latest one when not hovering).
  const [hover, setHover] = useState<OhlcPoint | null>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el || !points.length) return;
    // Intraday points carry epoch seconds. lightweight-charts renders those in
    // UTC by default — format ticks and the crosshair in the COMPUTER'S local
    // timezone instead.
    const intraday = typeof points[0].t === "number";
    const localTick = (time: Time, type: TickMarkType): string => {
      const d = new Date((time as number) * 1000);
      if (type === TickMarkType.Year) return String(d.getFullYear());
      if (type === TickMarkType.Month)
        return d.toLocaleString(undefined, { month: "short" });
      if (type === TickMarkType.DayOfMonth)
        return d.toLocaleString(undefined, { month: "2-digit", day: "2-digit" });
      return d.toLocaleTimeString(undefined, {
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      });
    };

    const chart = createChart(el, {
      height,
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "#8d8675",
        fontFamily: "'JetBrains Mono', monospace",
        fontSize: 10,
        // No clickable logo on the canvas; the library is credited as text in
        // the legend line below instead (its license allows either form).
        attributionLogo: false,
      },
      grid: {
        vertLines: { color: "rgba(141, 134, 117, 0.08)" },
        horzLines: { color: "rgba(141, 134, 117, 0.08)" },
      },
      rightPriceScale: { borderColor: "rgba(141, 134, 117, 0.25)" },
      timeScale: {
        borderColor: "rgba(141, 134, 117, 0.25)",
        timeVisible: intraday,
        secondsVisible: false,
        ...(intraday && { tickMarkFormatter: localTick }),
      },
      ...(intraday && {
        localization: { timeFormatter: (t: Time) => fmtTime(t as number) },
      }),
      crosshair: {
        horzLine: { color: AMBER, labelBackgroundColor: AMBER },
        vertLine: { color: AMBER, labelBackgroundColor: AMBER },
      },
    });

    const candles = chart.addSeries(CandlestickSeries, {
      upColor: UP,
      downColor: DOWN,
      wickUpColor: UP,
      wickDownColor: DOWN,
      borderVisible: false,
    });
    candles.setData(
      points.map((p) => ({ time: p.t as Time, open: p.o, high: p.h, low: p.l, close: p.c })),
    );

    const volume = chart.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" },
      priceScaleId: "vol",
      lastValueVisible: false,
      priceLineVisible: false,
    });
    chart.priceScale("vol").applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
    volume.setData(
      points.map((p) => ({
        time: p.t as Time,
        value: p.v,
        color: p.c >= p.o ? "rgba(63,174,106,0.35)" : "rgba(229,72,77,0.35)",
      })),
    );

    for (const [window, color] of [
      [50, AMBER],
      [200, CYAN],
    ] as const) {
      const data = smaLine(points, window);
      if (!data.length) continue;
      const line = chart.addSeries(LineSeries, {
        color,
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: false,
      });
      line.setData(data);
    }

    // Crosshair readout: report the candle under the cursor to the legend.
    const byTime = new Map(points.map((p) => [p.t, p]));
    chart.subscribeCrosshairMove((param) => {
      const t = param.time as string | number | undefined;
      setHover((t !== undefined && byTime.get(t)) || null);
    });

    chart.timeScale().fitContent();
    return () => chart.remove();
  }, [points, height]);

  // Hovered candle, or the latest one when the cursor is off the chart.
  const p = hover ?? points[points.length - 1];
  const up = p ? p.c >= p.o : true;

  return (
    <div className="relative">
      {p && (
        <div className="pointer-events-none absolute left-2 top-1 z-10 flex flex-wrap gap-x-3 bg-card/85 px-1.5 py-0.5 font-mono text-[0.6875rem]">
          <span className="text-muted-foreground">{fmtTime(p.t)}</span>
          <span>
            <span className="text-muted-foreground">O</span> {p.o.toFixed(2)}
          </span>
          <span>
            <span className="text-muted-foreground">H</span> {p.h.toFixed(2)}
          </span>
          <span>
            <span className="text-muted-foreground">L</span> {p.l.toFixed(2)}
          </span>
          <span className={cn("font-bold", up ? "text-up" : "text-down")}>
            <span className="font-normal text-muted-foreground">C</span> {p.c.toFixed(2)}{" "}
            ({(((p.c - p.o) / p.o) * 100).toFixed(2)}%)
          </span>
          <span className="text-muted-foreground">VOL {fmtVol(p.v)}</span>
        </div>
      )}
      <div ref={ref} style={{ height }} />
      <div className="mt-1 flex gap-4 font-mono text-[0.625rem] text-muted-foreground">
        <span>
          <span style={{ color: AMBER }}>—</span> SMA 50
        </span>
        <span>
          <span style={{ color: CYAN }}>—</span> SMA 200
        </span>
        <span>▮ volume</span>
        <span className="ml-auto text-muted-foreground/60">
          chart: TradingView lightweight-charts
        </span>
      </div>
    </div>
  );
}

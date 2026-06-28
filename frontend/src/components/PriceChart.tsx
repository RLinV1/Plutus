import { Area, AreaChart, ResponsiveContainer, Tooltip, YAxis } from "recharts";
import type { PricePoint } from "../types";
import { fmtUSD } from "../utils";

/** Floating label at the cursor showing the price + date at that point. */
function HoverTip({ active, payload }: { active?: boolean; payload?: any[] }) {
  if (!active || !payload || !payload.length) return null;
  const p = payload[0].payload as PricePoint;
  return (
    <div className="rounded-lg border border-border bg-popover px-3 py-2 shadow-xl">
      <div className="tnum text-sm font-bold">{fmtUSD(p.v)}</div>
      <div className="text-xs text-muted-foreground">
        {new Date(p.t).toLocaleDateString(undefined, {
          month: "short",
          day: "numeric",
          year: "numeric",
        })}
      </div>
    </div>
  );
}

interface Props {
  points: PricePoint[];
  positive: boolean;
  /** Fires with the hovered point (Robinhood-style) or null when the cursor leaves. */
  onHover?: (p: PricePoint | null) => void;
}

export function PriceChart({ points, positive, onHover }: Props) {
  if (!points || points.length < 2) {
    return (
      <div className="grid h-[300px] place-items-center text-sm text-muted-foreground">
        No price history to chart.
      </div>
    );
  }

  const color = positive ? "hsl(var(--up))" : "hsl(var(--down))";
  const vals = points.map((p) => p.v);
  const min = Math.min(...vals);
  const max = Math.max(...vals);
  const pad = (max - min) * 0.08 || 1;

  return (
    <div className="h-[300px] w-full select-none">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart
          data={points}
          margin={{ top: 10, right: 0, left: 0, bottom: 0 }}
          onMouseMove={(state: any) => {
            const p = state?.activePayload?.[0]?.payload as PricePoint | undefined;
            if (p && onHover) onHover(p);
          }}
          onMouseLeave={() => onHover?.(null)}
        >
          <defs>
            <linearGradient id="price-fill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity={0.3} />
              <stop offset="95%" stopColor={color} stopOpacity={0} />
            </linearGradient>
          </defs>
          <YAxis hide domain={[min - pad, max + pad]} />
          <Tooltip
            cursor={{
              stroke: "hsl(var(--muted-foreground))",
              strokeWidth: 1,
              strokeDasharray: "4 4",
            }}
            content={<HoverTip />}
            isAnimationActive={false}
          />
          <Area
            type="monotone"
            dataKey="v"
            stroke={color}
            strokeWidth={2}
            fill="url(#price-fill)"
            isAnimationActive={false}
            activeDot={{
              r: 4,
              fill: color,
              stroke: "hsl(var(--background))",
              strokeWidth: 2,
            }}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

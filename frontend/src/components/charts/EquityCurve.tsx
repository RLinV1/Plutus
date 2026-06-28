import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { PricePoint } from "../../types";
import { fmtUSD } from "../../utils";

/** The account's value over time. Amber line — this is THE portfolio series,
 *  not an up/down judgment, so it doesn't get the green/red treatment. */
export function EquityCurveChart({
  points,
  height = 260,
  money = true,
}: {
  points: PricePoint[];
  height?: number;
  money?: boolean;
}) {
  if (!points.length) return null;
  const fmt = (v: number) => (money ? fmtUSD(v, 0) : v.toFixed(1));
  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={points} margin={{ top: 6, right: 6, bottom: 0, left: 0 }}>
        <defs>
          <linearGradient id="equityFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#ffae0a" stopOpacity={0.28} />
            <stop offset="100%" stopColor="#ffae0a" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke="rgba(141,134,117,0.08)" vertical={false} />
        <XAxis
          dataKey="t"
          tick={{ fill: "#8d8675", fontSize: 10, fontFamily: "JetBrains Mono" }}
          tickLine={false}
          axisLine={false}
          minTickGap={60}
        />
        <YAxis
          tick={{ fill: "#8d8675", fontSize: 10, fontFamily: "JetBrains Mono" }}
          tickLine={false}
          axisLine={false}
          width={62}
          domain={["auto", "auto"]}
          tickFormatter={fmt}
        />
        <Tooltip
          contentStyle={{
            background: "hsl(40 12% 7%)",
            border: "1px solid hsl(40 10% 15%)",
            borderRadius: 4,
            fontFamily: "JetBrains Mono",
            fontSize: 12,
          }}
          labelStyle={{ color: "#8d8675" }}
          formatter={(v) => [fmt(Number(v)), money ? "value" : "index"]}
        />
        <Area
          type="monotone"
          dataKey="v"
          stroke="#ffae0a"
          strokeWidth={1.5}
          fill="url(#equityFill)"
          isAnimationActive={false}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}

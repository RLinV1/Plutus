import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import type { Holding } from "../../types";
import { fmtUSD } from "../../utils";

// A sequential ramp (no reds/greens — those mean up/down here).
const RAMP = [
  "#ffae0a",
  "#e09a2a",
  "#c08738",
  "#a1763f",
  "#856640",
  "#6b573d",
  "#544937",
  "#403c2f",
];

export function AllocationDonut({ holdings }: { holdings: Holding[] }) {
  const data = holdings.map((h) => ({
    name: h.ticker,
    value: h.market_value,
    weight: h.weight ?? 0,
  }));
  return (
    <div className="flex items-center gap-4">
      <div className="h-44 w-44 shrink-0">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={data}
              dataKey="value"
              nameKey="name"
              innerRadius="62%"
              outerRadius="95%"
              stroke="hsl(40 12% 6%)"
              isAnimationActive={false}
            >
              {data.map((_, i) => (
                <Cell key={i} fill={RAMP[i % RAMP.length]} />
              ))}
            </Pie>
            <Tooltip
              contentStyle={{
                background: "hsl(40 12% 7%)",
                border: "1px solid hsl(40 10% 15%)",
                borderRadius: 4,
                fontFamily: "JetBrains Mono",
                fontSize: 12,
              }}
              formatter={(v, name) => [fmtUSD(Number(v)), String(name)]}
            />
          </PieChart>
        </ResponsiveContainer>
      </div>
      <ul className="space-y-1 font-mono text-xs">
        {data.map((d, i) => (
          <li key={d.name} className="flex items-center gap-2">
            <span
              className="inline-block h-2 w-2"
              style={{ background: RAMP[i % RAMP.length] }}
            />
            <span className="w-12 font-bold">{d.name}</span>
            <span className="tnum text-muted-foreground">
              {(d.weight * 100).toFixed(1)}%
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

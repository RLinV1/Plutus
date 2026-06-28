/** Pure-CSS correlation grid: cell color encodes how much two holdings move
 *  together (amber = in lockstep, dark = independent). No chart lib needed. */
export function CorrelationHeatmap({
  tickers,
  matrix,
}: {
  tickers: string[];
  matrix: (number | null)[][];
}) {
  if (tickers.length < 2) {
    return (
      <p className="text-xs text-muted-foreground">
        Hold at least two positions to see how they move together.
      </p>
    );
  }
  const color = (c: number | null) => {
    if (c == null) return "transparent";
    const t = Math.max(0, Math.min(1, (c + 1) / 2)); // -1..1 -> 0..1
    return `hsl(39 100% 52% / ${(t * 0.85).toFixed(2)})`;
  };
  return (
    <div
      className="grid gap-px font-mono text-[0.625rem]"
      style={{ gridTemplateColumns: `3.2rem repeat(${tickers.length}, minmax(2.4rem, 1fr))` }}
    >
      <div />
      {tickers.map((t) => (
        <div key={`h-${t}`} className="px-1 py-0.5 text-center font-bold text-muted-foreground">
          {t}
        </div>
      ))}
      {tickers.map((row, i) => (
        <RowCells key={row} row={row} i={i} tickers={tickers} matrix={matrix} color={color} />
      ))}
    </div>
  );
}

function RowCells({
  row,
  i,
  tickers,
  matrix,
  color,
}: {
  row: string;
  i: number;
  tickers: string[];
  matrix: (number | null)[][];
  color: (c: number | null) => string;
}) {
  return (
    <>
      <div className="px-1 py-1 font-bold text-muted-foreground">{row}</div>
      {tickers.map((col, j) => {
        const c = matrix[i]?.[j] ?? null;
        return (
          <div
            key={`${row}-${col}`}
            className="tnum py-1 text-center text-foreground/90"
            style={{ background: color(c) }}
            title={`${row} vs ${col}: ${c?.toFixed(2) ?? "—"}`}
          >
            {c != null ? c.toFixed(2) : "—"}
          </div>
        );
      })}
    </>
  );
}

export const fmtUSD = (n: number | null | undefined, dp = 2): string =>
  n === null || n === undefined || Number.isNaN(n)
    ? "—"
    : n.toLocaleString("en-US", {
        style: "currency",
        currency: "USD",
        minimumFractionDigits: dp,
        maximumFractionDigits: dp,
      });

export const fmtPct = (frac: number | null | undefined, dp = 2): string =>
  frac === null || frac === undefined || Number.isNaN(frac)
    ? "—"
    : `${(frac * 100).toFixed(dp)}%`;

export const fmtSignedPct = (frac: number | null | undefined, dp = 2): string =>
  frac === null || frac === undefined || Number.isNaN(frac)
    ? "—"
    : `${frac >= 0 ? "+" : ""}${(frac * 100).toFixed(dp)}%`;

export const fmtNum = (n: number | null | undefined, dp = 1): string =>
  n === null || n === undefined || Number.isNaN(n) ? "—" : n.toFixed(dp);

export const titleCase = (s: string): string =>
  s ? s.charAt(0).toUpperCase() + s.slice(1) : s;

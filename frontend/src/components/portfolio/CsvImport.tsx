import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "../../api";
import type { CsvParseResult } from "../../types";
import { Button } from "@/components/ui/button";
import { fmtUSD } from "../../utils";

const EXAMPLE_CSV = `Run Date,Action,Symbol,Quantity,Price ($),Commission ($)
02/01/2021,YOU BOUGHT,AAPL,10,$130.00,$4.95
02/01/2021,YOU BOUGHT,MSFT,8,$230.00,$4.95
03/01/2021,YOU BOUGHT,NVDA,12,$130.00,
08/02/2021,YOU SOLD,NVDA,-2,$180.00,`;

/** CSV import with a mandatory dry-run preview: paste/drop a brokerage export,
 *  see exactly what will be recorded (and which lines failed), THEN commit. */
export function CsvImport({ portfolio }: { portfolio: string }) {
  const qc = useQueryClient();
  const [text, setText] = useState("");
  const [preview, setPreview] = useState<CsvParseResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState("");

  const dryRun = async () => {
    setBusy(true);
    setDone("");
    try {
      setPreview(await api.importCsv(portfolio, text, false));
    } finally {
      setBusy(false);
    }
  };

  const commit = async () => {
    setBusy(true);
    try {
      const res = await api.importCsv(portfolio, text, true);
      if (res.committed) {
        setDone(`Imported ${res.imported} transaction(s).`);
        setText("");
        setPreview(null);
        qc.invalidateQueries({ queryKey: ["portfolio"] });
      } else {
        setPreview(res);
      }
    } finally {
      setBusy(false);
    }
  };

  const onFile = (f: File | undefined) => {
    if (!f) return;
    f.text().then((t) => {
      setText(t);
      setPreview(null);
      setDone("");
    });
  };

  return (
    <div className="min-w-0 space-y-2">
      <textarea
        aria-label="CSV content"
        value={text}
        onChange={(e) => {
          setText(e.target.value);
          setPreview(null);
        }}
        placeholder={
          "Paste a brokerage CSV (or choose a file).\nNeeds at least: ticker/symbol, shares/quantity, price.\nNegative quantities and 'YOU SOLD' actions are understood as sells."
        }
        className="h-28 w-full max-w-full resize-y border border-input bg-background p-2 font-mono text-[0.6875rem] outline-none focus-visible:ring-1 focus-visible:ring-ring"
      />
      <input
        type="file"
        accept=".csv,text/csv"
        aria-label="Choose CSV file"
        onChange={(e) => onFile(e.target.files?.[0])}
        className="block w-full max-w-full min-w-0 text-xs text-muted-foreground file:mr-2 file:border file:border-border file:bg-secondary file:px-2 file:py-1 file:font-mono file:text-xs file:text-foreground"
      />
      <div className="flex flex-wrap items-center gap-2">
        <Button
          size="sm"
          variant="ghost"
          onClick={() => {
            setText(EXAMPLE_CSV);
            setPreview(null);
            setDone("");
          }}
          title="Fill in a sample Fidelity-style export to see the expected format"
        >
          Example
        </Button>
        <Button size="sm" variant="outline" onClick={dryRun} disabled={!text.trim() || busy}>
          Preview
        </Button>
        <Button
          size="sm"
          onClick={commit}
          disabled={busy || !preview || !preview.rows.length}
          title={!preview ? "Preview first — imports are never silent" : ""}
        >
          Import {preview?.rows.length ?? 0} row(s)
        </Button>
      </div>
      {done && <p className="font-mono text-[0.6875rem] text-up">{done}</p>}
      {preview && (
        <div className="max-h-44 overflow-auto border border-border">
          <table className="w-full font-mono text-[0.6875rem]">
            <thead>
              <tr className="micro border-b border-border text-left">
                <th className="px-2 py-1">DATE</th>
                <th className="px-2 py-1">SIDE</th>
                <th className="px-2 py-1">TICKER</th>
                <th className="px-2 py-1 text-right">SHARES</th>
                <th className="px-2 py-1 text-right">PRICE</th>
              </tr>
            </thead>
            <tbody>
              {preview.rows.map((r, i) => (
                <tr key={i} className="border-b border-border/40">
                  <td className="px-2 py-1 text-muted-foreground">{r.trade_date}</td>
                  <td className={r.side === "BUY" ? "px-2 py-1 text-up" : "px-2 py-1 text-down"}>
                    {r.side}
                  </td>
                  <td className="px-2 py-1 font-bold">{r.ticker}</td>
                  <td className="tnum px-2 py-1 text-right">{r.shares}</td>
                  <td className="tnum px-2 py-1 text-right">{fmtUSD(r.price)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {preview.errors.length > 0 && (
            <ul className="space-y-0.5 p-2 font-mono text-[0.6875rem] text-down">
              {preview.errors.map((e, i) => (
                <li key={i}>⚠ {e}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

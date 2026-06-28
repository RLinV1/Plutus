import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../../api";
import { TickerInput } from "../TickerInput";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

export interface TradePrefill {
  side: "BUY" | "SELL";
  ticker: string;
  shares?: number;
  price?: number;
  /** Changes on every request so the same row can prefill twice in a row. */
  nonce: number;
}

/** Record a buy or sell. On success every portfolio query refetches.
 *  ``prefill`` lets the holdings table's quick-SELL buttons load the form;
 *  ``holdings`` restricts the SELL-side ticker search to what you own. */
export function TransactionForm({
  portfolio,
  prefill,
  holdings = [],
}: {
  portfolio: string;
  prefill?: TradePrefill | null;
  holdings?: { ticker: string; shares: number }[];
}) {
  const qc = useQueryClient();
  const [side, setSide] = useState<"BUY" | "SELL">("BUY");
  const [ticker, setTicker] = useState("");
  const [shares, setShares] = useState("");
  const [price, setPrice] = useState("");
  const [msg, setMsg] = useState("");

  useEffect(() => {
    if (!prefill) return;
    setSide(prefill.side);
    setTicker(prefill.ticker);
    setShares(prefill.shares != null ? String(prefill.shares) : "");
    setPrice(prefill.price != null ? String(prefill.price) : "");
    setMsg("");
  }, [prefill]);

  const mut = useMutation({
    mutationFn: () =>
      api.addTransaction(portfolio, {
        ticker: ticker.trim().toUpperCase(),
        side,
        shares: Number(shares),
        price: Number(price),
        // No date picker — trades are recorded as of today (the backend default).
      } as never),
    onSuccess: (res) => {
      if ((res as { error?: string }).error) {
        setMsg((res as { error?: string }).error!);
        return;
      }
      setMsg(`Recorded: ${side} ${shares} ${ticker.toUpperCase()}`);
      setTicker("");
      setShares("");
      setPrice("");
      qc.invalidateQueries({ queryKey: ["portfolio"] });
    },
    onError: (e: Error) => setMsg(e.message),
  });

  // Selling something you don't hold is always a mistake — block it client-side.
  const heldTickers = holdings.filter((h) => h.shares > 0);
  const sellOptions = heldTickers.map((h) => ({
    symbol: h.ticker,
    name: `${h.shares} sh held`,
  }));
  const sellUnknown =
    side === "SELL" &&
    ticker.trim().length > 0 &&
    !heldTickers.some((h) => h.ticker === ticker.trim().toUpperCase());

  const valid =
    ticker.trim().length > 0 && Number(shares) > 0 && Number(price) > 0 && !sellUnknown;

  return (
    <form
      className="space-y-2"
      onSubmit={(e) => {
        e.preventDefault();
        if (valid && !mut.isPending) mut.mutate();
      }}
    >
      <div className="flex gap-1">
        {(["BUY", "SELL"] as const).map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => setSide(s)}
            className={cn(
              "h-8 flex-1 border font-mono text-xs font-bold tracking-widest",
              side === s
                ? s === "BUY"
                  ? "border-up bg-up/15 text-up"
                  : "border-down bg-down/15 text-down"
                : "border-border text-muted-foreground hover:text-foreground",
            )}
          >
            {s}
          </button>
        ))}
      </div>
      <TickerInput
        value={ticker}
        onChange={setTicker}
        placeholder={side === "SELL" ? "Which holding to sell…" : "Ticker or company…"}
        options={side === "SELL" ? sellOptions : undefined}
      />
      {sellUnknown && (
        <p className="font-mono text-[0.6875rem] text-down">
          You don't hold {ticker.trim().toUpperCase()} — pick one of your holdings.
        </p>
      )}
      <div className="grid grid-cols-2 gap-2">
        <Input
          aria-label="Shares"
          placeholder="Shares"
          type="number"
          min="0"
          step="any"
          value={shares}
          onChange={(e) => setShares(e.target.value)}
          className="font-mono"
        />
        <Input
          aria-label="Price per share"
          placeholder="Price $"
          type="number"
          min="0"
          step="any"
          value={price}
          onChange={(e) => setPrice(e.target.value)}
          className="font-mono"
        />
      </div>
      <Button type="submit" disabled={!valid || mut.isPending} className="w-full">
        {mut.isPending ? "Recording…" : `Record ${side.toLowerCase()}`}
      </Button>
      {msg && <p className="font-mono text-[0.6875rem] text-muted-foreground">{msg}</p>}
    </form>
  );
}

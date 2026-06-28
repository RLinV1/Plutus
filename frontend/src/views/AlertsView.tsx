import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api";
import { Panel } from "../components/terminal/Panel";
import { NotificationsFeed } from "../components/portfolio/NotificationsFeed";
import { TickerInput } from "../components/TickerInput";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

const RULE_TYPES: { id: string; label: string; hint: string }[] = [
  { id: "price_above", label: "Price above $X", hint: "fires when the price reaches your level" },
  { id: "price_below", label: "Price below $X", hint: "fires when the price falls to your level" },
  { id: "pct_move", label: "Daily move > X%", hint: "fires on a big day in either direction" },
  { id: "rsi_above", label: "RSI above X", hint: "overbought territory (70+ is the classic line)" },
  { id: "rsi_below", label: "RSI below X", hint: "oversold territory (30- is the classic line)" },
  { id: "drawdown", label: "Down X% from high", hint: "fires when it falls X% off its recent peak" },
  { id: "news_volume", label: "News volume ≥ X", hint: "unusual number of relevant articles" },
];

export default function AlertsView() {
  const qc = useQueryClient();
  const [ticker, setTicker] = useState("");
  const [ruleType, setRuleType] = useState("price_above");
  const [threshold, setThreshold] = useState("");
  const [msg, setMsg] = useState("");

  const { data: rules = [] } = useQuery({ queryKey: ["alerts"], queryFn: api.alerts });

  const [busy, setBusy] = useState(false);

  const create = async () => {
    setMsg("");
    setBusy(true);
    try {
      const res = await api.addAlert({
        ticker: ticker.trim().toUpperCase(),
        rule_type: ruleType,
        threshold: Number(threshold),
      });
      if ((res as { error?: string }).error) {
        setMsg((res as { error?: string }).error!);
        return;
      }
      setMsg(`Armed: ${ticker.trim().toUpperCase()} ${ruleType} ${threshold}`);
      setTicker("");
      setThreshold("");
      qc.invalidateQueries({ queryKey: ["alerts"] });
    } catch (e) {
      // A failed request must never be silent — that's how rules get "lost".
      setMsg(`Couldn't save the rule: ${e instanceof Error ? e.message : e}`);
    } finally {
      setBusy(false);
    }
  };

  const selected = RULE_TYPES.find((r) => r.id === ruleType)!;

  return (
    <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
      <div className="space-y-3">
        <Panel tourId="alert-new" title="NEW TRIPWIRE">
          <div className="flex flex-wrap gap-1">
            {RULE_TYPES.map((r) => (
              <button
                key={r.id}
                onClick={() => setRuleType(r.id)}
                className={cn(
                  "border px-2 py-1 font-mono text-[0.6875rem]",
                  ruleType === r.id
                    ? "border-primary bg-primary/15 text-primary"
                    : "border-border text-muted-foreground hover:text-foreground",
                )}
              >
                {r.label}
              </button>
            ))}
          </div>
          <p className="mt-1.5 text-[0.6875rem] text-muted-foreground">{selected.hint}</p>
          <div className="mt-2 flex gap-2">
            <TickerInput
              value={ticker}
              onChange={setTicker}
              placeholder="Ticker or company…"
              className="w-44"
            />
            <Input
              aria-label="Threshold"
              placeholder="Threshold"
              type="number"
              step="any"
              className="w-32 font-mono"
              value={threshold}
              onChange={(e) => setThreshold(e.target.value)}
            />
            <Button onClick={create} disabled={busy || !ticker.trim() || !threshold}>
              {busy ? "Checking…" : "Arm it"}
            </Button>
          </div>
          {msg && (
            <p
              className={cn(
                "mt-1.5 font-mono text-[0.6875rem]",
                msg.startsWith("Armed") ? "text-up" : "text-down",
              )}
            >
              {msg}
            </p>
          )}
          <p className="mt-2 border-t border-border pt-2 text-[0.6875rem] text-muted-foreground">
            Rules are checked every ~20 seconds while the backend runs. After
            firing, a rule stays quiet for its cooldown (default 4h) so you
            aren't spammed while the condition holds.
          </p>
        </Panel>

        <Panel title={`ARMED RULES · ${rules.length}`}>
          {rules.length ? (
            <ul className="space-y-1 font-mono text-xs">
              {rules.map((r) => (
                <li key={r.id} className="flex items-center gap-2 border-b border-border/40 pb-1">
                  <button
                    role="switch"
                    aria-checked={r.enabled}
                    aria-label={`Turn rule ${r.id} ${r.enabled ? "off" : "on"}`}
                    title={r.enabled ? "Rule is ON — click to pause it" : "Rule is OFF — click to arm it"}
                    onClick={async () => {
                      await api.toggleAlert(r.id, !r.enabled);
                      qc.invalidateQueries({ queryKey: ["alerts"] });
                    }}
                    className={cn(
                      "w-12 shrink-0 border py-0.5 text-center font-mono text-[0.625rem] font-bold tracking-wider",
                      r.enabled
                        ? "border-up bg-up/20 text-up"
                        : "border-border bg-secondary text-muted-foreground line-through",
                    )}
                  >
                    {r.enabled ? "ON" : "OFF"}
                  </button>
                  <span className="w-14 font-bold">{r.ticker}</span>
                  <span className="text-muted-foreground">{r.rule_type}</span>
                  <span className="tnum">{r.threshold}</span>
                  {r.last_triggered_at && (
                    <span className="text-[0.625rem] text-muted-foreground">
                      last: {r.last_triggered_at.slice(0, 16).replace("T", " ")}
                    </span>
                  )}
                  <button
                    aria-label={`Delete rule ${r.id}`}
                    title="Delete this rule"
                    className="ml-auto grid h-7 w-7 shrink-0 place-items-center border border-border text-base leading-none text-muted-foreground hover:border-down/60 hover:bg-down/10 hover:text-down"
                    onClick={async () => {
                      await api.deleteAlert(r.id);
                      qc.invalidateQueries({ queryKey: ["alerts"] });
                    }}
                  >
                    ×
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-xs text-muted-foreground">No rules armed yet.</p>
          )}
        </Panel>
      </div>

      <Panel tourId="notifications" title="NOTIFICATIONS" bodyClassName="p-3">
        <NotificationsFeed />
      </Panel>
    </div>
  );
}

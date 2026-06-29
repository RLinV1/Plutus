import { useEffect } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../api";
import { useWorkspace } from "../../stores/workspace";
import type { BillingStatus, Plan } from "../../types";
import { cn } from "@/lib/utils";

// Display-only price labels. The REAL amounts are set on your Stripe Prices;
// edit these to match what you configured there.
const TIERS: {
  plan: Plan;
  name: string;
  price: string;
  cadence: string;
  tagline: string;
  highlight?: boolean;
  features: string[];
}[] = [
  {
    plan: "free",
    name: "Free",
    price: "$0",
    cadence: "forever",
    tagline: "Kick the tires.",
    features: [
      "AI research prompts",
      "Live market data & quotes",
      "Portfolio tracking with P&L",
      "Risk analytics — VaR, beta, Sharpe",
      "Scenario lab & stress tests",
      "Real-time alerts & watchlist",
    ],
  },
  {
    plan: "pro",
    name: "Pro",
    price: "$10",
    cadence: "/month",
    tagline: "For active research.",
    highlight: true,
    features: [
      "Everything in Free",
      "2× the daily AI research",
      "Priority response queue",
      "Full portfolio + scenario suite",
    ],
  },
  {
    plan: "pro_max",
    name: "Pro Max",
    price: "$20",
    cadence: "/month",
    tagline: "For power users.",
    features: [
      "Everything in Pro",
      "4× the daily AI research",
      "Highest daily allowance",
      "First access to new features",
    ],
  },
];

function Check() {
  return (
    <svg viewBox="0 0 20 20" className="mt-0.5 h-3.5 w-3.5 shrink-0 text-primary" fill="none">
      <path d="M4 10l4 4 8-9" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/** Full-screen plans & pricing page, shown at the #/pricing route. Elegant
 *  three-tier layout with per-plan benefits and Stripe checkout. */
export function PricingPage() {
  const open = useWorkspace((s) => s.billingOpen);
  const setBillingOpen = useWorkspace((s) => s.setBillingOpen);
  const close = () => setBillingOpen(false);

  const { data } = useQuery<BillingStatus>({
    queryKey: ["billing"],
    queryFn: api.billingStatus,
    enabled: open,
  });

  // Reflect the page in the URL (#/pricing) so it's shareable / deep-linkable.
  useEffect(() => {
    if (!open) return;
    if (window.location.hash !== "#/pricing") {
      window.history.pushState(null, "", "#/pricing");
    }
    return () => {
      if (window.location.hash === "#/pricing") {
        window.history.pushState(null, "", window.location.pathname + window.location.search);
      }
    };
  }, [open]);

  // Close on Escape.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && close();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  const checkout = useMutation({
    mutationFn: (plan: "pro" | "pro_max") => api.billingCheckout(plan),
    onSuccess: (r) => r.url && (window.location.href = r.url),
  });
  const portal = useMutation({
    mutationFn: () => api.billingPortal(),
    onSuccess: (r) => r.url && (window.location.href = r.url),
  });
  const qc = useQueryClient();
  const change = useMutation({
    mutationFn: (plan: "free" | "pro" | "pro_max") => api.billingChange(plan),
    onSuccess: (r) => {
      // No active sub → server returns a Checkout URL; otherwise it swapped the
      // plan in place, so just refresh the badge/status.
      if (r.url) window.location.href = r.url;
      else qc.invalidateQueries({ queryKey: ["billing"] });
    },
  });

  if (!open) return null;

  const current = data?.plan ?? "free";
  const limits = data?.limits ?? { free: 5, pro: 10, pro_max: 20 };
  const billingOn = data?.billing_enabled ?? false;
  const unlimited = data?.unlimited ?? false;
  const reachedLimit = !unlimited && data ? data.remaining <= 0 : false;
  const busy = checkout.isPending || portal.isPending || change.isPending;
  const err =
    (checkout.error as Error)?.message ||
    (portal.error as Error)?.message ||
    (change.error as Error)?.message ||
    null;

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto bg-background">
      {/* top bar */}
      <div className="sticky top-0 z-10 flex h-14 items-center justify-between border-b border-border bg-background/90 px-4 backdrop-blur">
        <span className="font-mono text-lg font-bold tracking-tight text-primary">▌PLUTUS</span>
        <button
          onClick={close}
          className="font-mono text-xs text-muted-foreground hover:text-foreground"
        >
          ✕ Back to terminal
        </button>
      </div>

      <div className="mx-auto max-w-5xl px-4 py-10">
        {/* hero */}
        <div className="mx-auto max-w-2xl text-center">
          <h1 className="font-mono text-2xl font-bold tracking-tight text-foreground sm:text-3xl">
            Choose your plan
          </h1>
          <p className="mt-2 font-mono text-xs text-muted-foreground">
            Plans differ by how many AI research prompts you get per day. Your
            allowance resets at <span className="text-foreground">00:00 UTC</span>.
          </p>
        </div>

        {unlimited && (
          <div className="mx-auto mt-6 max-w-md border border-primary/50 bg-primary/10 px-4 py-2 text-center font-mono text-xs text-primary">
            You have <b>unlimited</b> access — no daily cap. ∞
          </div>
        )}
        {reachedLimit && (
          <div className="mx-auto mt-6 max-w-md border border-down/50 bg-down/10 px-4 py-2 text-center font-mono text-xs text-down">
            You've used all {data?.limit} prompts today. Upgrade for a higher daily limit.
          </div>
        )}

        {/* tiers */}
        <div className="mt-8 grid grid-cols-1 gap-4 md:grid-cols-3">
          {TIERS.map((t) => {
            const isCurrent = !unlimited && t.plan === current;
            const perDay = limits[t.plan];
            return (
              <div
                key={t.plan}
                className={cn(
                  "relative flex flex-col border bg-card p-5",
                  t.highlight
                    ? "border-primary shadow-[0_0_30px_-10px_hsl(39,100%,52%)]"
                    : "border-border",
                )}
              >
                {t.highlight && (
                  <span className="absolute -top-2.5 left-5 bg-primary px-2 py-0.5 font-mono text-[0.5625rem] font-bold uppercase tracking-widest text-primary-foreground">
                    Most popular
                  </span>
                )}
                <div className="font-mono text-sm font-bold uppercase tracking-wider text-foreground">
                  {t.name}
                </div>
                <div className="font-mono text-[0.6875rem] text-muted-foreground">
                  {t.tagline}
                </div>

                <div className="mt-4 flex items-baseline gap-1">
                  <span className="font-mono text-3xl font-bold text-foreground">{t.price}</span>
                  <span className="font-mono text-xs text-muted-foreground">{t.cadence}</span>
                </div>

                <div className="mt-4 border-y border-border py-3 text-center">
                  <span className="font-mono text-2xl font-bold text-primary">{perDay}</span>
                  <span className="ml-1 font-mono text-[0.6875rem] text-muted-foreground">
                    AI prompts / day
                  </span>
                </div>

                <ul className="mt-4 space-y-2">
                  {t.features.map((f) => (
                    <li key={f} className="flex gap-2 font-mono text-[0.6875rem] text-muted-foreground">
                      <Check />
                      <span>{f}</span>
                    </li>
                  ))}
                </ul>

                <div className="mt-5 pt-2">{cta(t.plan)}</div>
              </div>
            );
          })}
        </div>

        {err && <p className="mt-5 text-center font-mono text-[0.6875rem] text-down">{err}</p>}
        {!billingOn && (
          <p className="mt-5 text-center font-mono text-[0.6875rem] text-muted-foreground">
            Paid upgrades aren't available right now.
          </p>
        )}

        {/* footer */}
        <div className="mt-10 flex flex-col items-center gap-2 text-center">
          {current !== "free" && billingOn && !unlimited && (
            <button
              disabled={busy}
              onClick={() => portal.mutate()}
              className="font-mono text-[0.6875rem] text-primary underline hover:text-primary/80 disabled:opacity-50"
            >
              Manage billing / cancel
            </button>
          )}
          <p className="font-mono text-[0.625rem] text-muted-foreground/70">
            🔒 Secure checkout via Stripe · cancel anytime · prices in USD
          </p>
          <p className="max-w-md font-mono text-[0.5625rem] text-muted-foreground/50">
            General information only — not personalized investment advice.
          </p>
        </div>
      </div>
    </div>
  );

  function cta(plan: Plan) {
    if (unlimited) {
      return (
        <div className="grid place-items-center border border-border py-2 font-mono text-[0.625rem] text-muted-foreground">
          INCLUDED
        </div>
      );
    }
    if (plan === current) {
      return (
        <div className="grid place-items-center border border-primary py-2 font-mono text-[0.625rem] font-bold text-primary">
          CURRENT PLAN
        </div>
      );
    }
    const onPaid = current !== "free";
    if (plan === "free") {
      // Paid users can downgrade back to free (cancels the subscription).
      if (!onPaid) {
        return (
          <div className="grid place-items-center border border-border py-2 font-mono text-[0.625rem] text-muted-foreground/60">
            —
          </div>
        );
      }
      return (
        <button
          disabled={busy || !billingOn}
          onClick={() => change.mutate("free")}
          className="grid w-full place-items-center border border-border py-2 font-mono text-[0.625rem] font-bold uppercase tracking-wider text-muted-foreground transition-colors hover:text-foreground disabled:opacity-50"
        >
          {busy ? "…" : "Downgrade to free"}
        </button>
      );
    }
    // Paid tier the user isn't on.
    return (
      <button
        disabled={busy || !billingOn}
        onClick={() =>
          onPaid
            ? change.mutate(plan as "pro" | "pro_max")
            : checkout.mutate(plan as "pro" | "pro_max")
        }
        className="grid w-full place-items-center bg-primary py-2 font-mono text-[0.625rem] font-bold uppercase tracking-wider text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-50"
      >
        {busy ? "…" : onPaid ? "Switch plan" : `Upgrade to ${TIERS.find((x) => x.plan === plan)?.name}`}
      </button>
    );
  }
}

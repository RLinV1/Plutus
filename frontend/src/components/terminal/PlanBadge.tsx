import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../../api";
import type { BillingStatus, Plan } from "../../types";
import { cn } from "@/lib/utils";

const PLAN_LABEL: Record<string, string> = {
  free: "FREE",
  pro: "PRO",
  pro_max: "PRO MAX",
  unlimited: "UNLIMITED",
};

/** Compact header pill showing today's prompt usage; click to open upgrades. */
export function PlanBadge({ onClick }: { onClick: () => void }) {
  const { data } = useQuery({
    queryKey: ["billing"],
    queryFn: api.billingStatus,
    staleTime: 15_000,
  });
  if (!data) return null;
  if (data.unlimited) {
    return (
      <span
        className="rounded border border-primary/50 px-2 py-1 font-mono text-[0.625rem] text-primary"
        title="No daily limit"
      >
        {PLAN_LABEL[data.plan] ?? "UNLIMITED"} ∞
      </span>
    );
  }
  const low = data.remaining <= 1;
  const none = data.remaining <= 0;
  return (
    <button
      onClick={onClick}
      title="View plans & usage"
      className={cn(
        "rounded border px-2 py-1 font-mono text-[0.625rem] tracking-wide transition-colors",
        none
          ? "border-down/60 text-down"
          : low
            ? "border-primary/60 text-primary"
            : "border-border text-muted-foreground hover:text-foreground",
      )}
    >
      {PLAN_LABEL[data.plan]} · {data.used}/{data.limit}
    </button>
  );
}

const TIERS: { plan: Plan; name: string; blurb: string }[] = [
  { plan: "free", name: "Free", blurb: "Get started" },
  { plan: "pro", name: "Pro", blurb: "For regulars" },
  { plan: "pro_max", name: "Pro Max", blurb: "Power users" },
];

/** Plan picker modal: shows daily limits per tier and starts Stripe Checkout. */
export function UpgradeDialog({
  open,
  onClose,
  reachedLimit,
}: {
  open: boolean;
  onClose: () => void;
  reachedLimit?: boolean;
}) {
  const { data } = useQuery<BillingStatus>({
    queryKey: ["billing"],
    queryFn: api.billingStatus,
    enabled: open,
  });
  const [err, setErr] = useState<string | null>(null);

  const checkout = useMutation({
    mutationFn: (plan: "pro" | "pro_max") => api.billingCheckout(plan),
    onSuccess: (r) => {
      if (r.url) window.location.href = r.url;
    },
    onError: (e: unknown) => setErr((e as Error)?.message ?? "Checkout failed."),
  });
  const portal = useMutation({
    mutationFn: () => api.billingPortal(),
    onSuccess: (r) => {
      if (r.url) window.location.href = r.url;
    },
    onError: (e: unknown) => setErr((e as Error)?.message ?? "Could not open billing."),
  });

  if (!open) return null;
  const current = data?.plan ?? "free";
  const limits = data?.limits ?? { free: 5, pro: 10, pro_max: 20 };
  const billingOn = data?.billing_enabled ?? false;
  const busy = checkout.isPending || portal.isPending;

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-black/70 p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-2xl border border-primary/40 bg-popover p-5 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-1 flex items-baseline justify-between">
          <h2 className="font-mono text-sm font-bold tracking-wide text-primary">
            {reachedLimit ? "DAILY LIMIT REACHED" : "PLANS & USAGE"}
          </h2>
          <button
            onClick={onClose}
            className="font-mono text-xs text-muted-foreground hover:text-foreground"
          >
            ✕
          </button>
        </div>
        <p className="mb-4 font-mono text-[0.6875rem] text-muted-foreground">
          {reachedLimit
            ? "You've used all of today's AI prompts. Upgrade for a higher daily limit — it resets at 00:00 UTC."
            : "AI prompts per day by plan. Limits reset at 00:00 UTC."}
        </p>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          {TIERS.map((t) => {
            const isCurrent = t.plan === current;
            return (
              <div
                key={t.plan}
                className={cn(
                  "flex flex-col border p-3",
                  isCurrent ? "border-primary" : "border-border",
                )}
              >
                <div className="font-mono text-xs font-bold text-foreground">
                  {t.name}
                </div>
                <div className="font-mono text-[0.625rem] text-muted-foreground">
                  {t.blurb}
                </div>
                <div className="my-3 font-mono text-2xl font-bold text-primary">
                  {limits[t.plan]}
                  <span className="ml-1 text-xs font-normal text-muted-foreground">
                    /day
                  </span>
                </div>
                {isCurrent ? (
                  <span className="mt-auto grid place-items-center border border-border px-2 py-1.5 font-mono text-[0.625rem] text-muted-foreground">
                    CURRENT
                  </span>
                ) : t.plan === "free" ? (
                  <span className="mt-auto grid place-items-center px-2 py-1.5 font-mono text-[0.625rem] text-muted-foreground/60">
                    —
                  </span>
                ) : (
                  <button
                    disabled={busy || !billingOn}
                    onClick={() => {
                      setErr(null);
                      checkout.mutate(t.plan as "pro" | "pro_max");
                    }}
                    className="mt-auto grid place-items-center bg-primary px-2 py-1.5 font-mono text-[0.625rem] font-bold uppercase tracking-wider text-primary-foreground disabled:opacity-50"
                  >
                    {busy ? "…" : "Upgrade"}
                  </button>
                )}
              </div>
            );
          })}
        </div>

        {!billingOn && (
          <p className="mt-3 font-mono text-[0.625rem] text-down">
            Upgrades aren't available right now (billing not configured).
          </p>
        )}
        {err && (
          <p className="mt-3 font-mono text-[0.625rem] text-down">{err}</p>
        )}

        {current !== "free" && billingOn && (
          <button
            disabled={busy}
            onClick={() => {
              setErr(null);
              portal.mutate();
            }}
            className="mt-4 font-mono text-[0.625rem] text-muted-foreground underline hover:text-foreground disabled:opacity-50"
          >
            Manage billing / cancel
          </button>
        )}
      </div>
    </div>
  );
}

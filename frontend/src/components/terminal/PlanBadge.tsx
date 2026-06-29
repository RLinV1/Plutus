import { useQuery } from "@tanstack/react-query";
import { api } from "../../api";
import { useWorkspace } from "../../stores/workspace";
import type { Plan } from "../../types";
import { cn } from "@/lib/utils";

export const PLAN_LABEL: Record<string, string> = {
  free: "FREE",
  pro: "PRO",
  pro_max: "PRO MAX",
  unlimited: "UNLIMITED",
};

/** Compact header pill showing today's prompt usage; click opens the pricing
 *  page (#/pricing). Always clickable, even when unlimited. */
export function PlanBadge() {
  const setBillingOpen = useWorkspace((s) => s.setBillingOpen);
  const { data } = useQuery({
    queryKey: ["billing"],
    queryFn: api.billingStatus,
    staleTime: 15_000,
  });
  if (!data) return null;

  const open = () => setBillingOpen(true);

  if (data.unlimited) {
    return (
      <button
        onClick={open}
        className="rounded border border-primary/50 px-2 py-1 font-mono text-[0.625rem] text-primary hover:bg-primary/10"
        title="View plans"
      >
        {PLAN_LABEL[data.plan] ?? "UNLIMITED"} ∞
      </button>
    );
  }
  const low = data.remaining <= 1;
  const none = data.remaining <= 0;
  return (
    <button
      onClick={open}
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
      {(PLAN_LABEL[data.plan] ?? data.plan.toUpperCase())} · {data.used}/{data.limit}
    </button>
  );
}

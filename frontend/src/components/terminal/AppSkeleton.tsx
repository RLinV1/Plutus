import { Skeleton } from "@/components/ui/skeleton";
import type { View } from "../../stores/workspace";

/* -------------------------------------------------------------------------- */
/* Per-tab content skeletons                                                  */
/* Each mirrors the rough layout of its view so the code-split chunk load     */
/* flashes a shape that matches what's about to render — not a generic block. */
/* -------------------------------------------------------------------------- */

function ResearchSkeleton() {
  return (
    <div className="space-y-3">
      <div className="flex gap-3">
        <Skeleton className="h-8 w-44" />
        <Skeleton className="h-8 w-24" />
        <Skeleton className="h-8 w-24" />
      </div>
      <Skeleton className="h-80 w-full" />
      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        <Skeleton className="h-32" />
        <Skeleton className="h-32" />
        <Skeleton className="h-32" />
      </div>
    </div>
  );
}

function MarketSkeleton() {
  return (
    <div className="space-y-3">
      {/* index strip */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-20" />
        ))}
      </div>
      {/* movers */}
      <div className="flex gap-2">
        <Skeleton className="h-7 w-24" />
        <Skeleton className="h-7 w-24" />
        <Skeleton className="h-7 w-28" />
      </div>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        <Skeleton className="h-64" />
        <Skeleton className="h-64" />
        <Skeleton className="h-64" />
      </div>
    </div>
  );
}

function PortfolioSkeleton() {
  return (
    <div className="space-y-3">
      {/* total / P&L tiles */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-20" />
        ))}
      </div>
      {/* equity curve */}
      <Skeleton className="h-64 w-full" />
      {/* holdings table + allocation */}
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
        <Skeleton className="h-72 lg:col-span-2" />
        <Skeleton className="h-72" />
      </div>
    </div>
  );
}

function PaperSkeleton() {
  return (
    <div className="space-y-3">
      {/* account summary tiles */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-20" />
        ))}
      </div>
      {/* trade form */}
      <Skeleton className="h-32 w-full" />
      {/* positions table */}
      <Skeleton className="h-56 w-full" />
    </div>
  );
}

function ScenarioSkeleton() {
  return (
    <div className="space-y-3">
      {/* scenario picker cards */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className="h-24" />
        ))}
      </div>
      {/* result panel */}
      <Skeleton className="h-72 w-full" />
    </div>
  );
}

function AlertsSkeleton() {
  return (
    <div className="space-y-3">
      {/* add-rule bar */}
      <Skeleton className="h-12 w-full" />
      {/* rule rows */}
      <div className="space-y-2">
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className="h-12 w-full" />
        ))}
      </div>
    </div>
  );
}

function AskSkeleton() {
  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <Skeleton className="ml-auto h-10 w-2/3" />
      <Skeleton className="h-24 w-5/6" />
      <Skeleton className="ml-auto h-10 w-1/2" />
      <Skeleton className="h-16 w-4/6" />
      <Skeleton className="mt-6 h-11 w-full" />
    </div>
  );
}

/** Content-area skeleton, shaped to the view whose code-split chunk is loading.
 *  Defaults to the research layout when no view is given. */
export function ViewSkeleton({ view }: { view?: View }) {
  switch (view) {
    case "market":
      return <MarketSkeleton />;
    case "portfolio":
      return <PortfolioSkeleton />;
    case "paper":
      return <PaperSkeleton />;
    case "scenario":
      return <ScenarioSkeleton />;
    case "alerts":
      return <AlertsSkeleton />;
    case "ask":
      return <AskSkeleton />;
    case "research":
    default:
      return <ResearchSkeleton />;
  }
}

/** Neutral, branded splash for the moment auth state is still resolving (and
 *  during sign-out). We do NOT yet know if the user is signed in, so showing a
 *  full dashboard skeleton here would wrongly imply a logged-in shell — that's
 *  what caused the dashboard to flash on sign-out. Keep this content-agnostic. */
export function BootSplash() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-3 bg-background">
      <div className="animate-pulse font-mono text-3xl font-bold tracking-tight text-primary">
        ▌PLUTUS
      </div>
      <div className="font-mono text-[0.65rem] tracking-wider text-muted-foreground">
        Loading…
      </div>
    </div>
  );
}

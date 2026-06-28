import { Skeleton } from "@/components/ui/skeleton";

/** Content-area skeleton: a chart block + a row of cards. Used as the Suspense
 *  fallback while a view's code-split chunk streams in. */
export function ViewSkeleton() {
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

/** Full-page skeleton mirroring the terminal shell (tape · header · content ·
 *  status bar). Shown while the app boots and while Clerk initializes, so a
 *  refresh never flashes a black screen. */
export function AppSkeleton() {
  return (
    <div className="flex min-h-screen flex-col bg-background">
      {/* ticker tape */}
      <div className="flex h-8 items-center gap-6 overflow-hidden border-b border-border bg-card px-3">
        {Array.from({ length: 10 }).map((_, i) => (
          <Skeleton key={i} className="h-3 w-24 shrink-0" />
        ))}
      </div>
      {/* header */}
      <div className="flex h-12 items-center gap-3 border-b border-border bg-card px-3">
        <Skeleton className="h-5 w-28" />
        <div className="ml-4 hidden gap-2 sm:flex">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-5 w-16" />
          ))}
        </div>
        <div className="ml-auto flex gap-2">
          <Skeleton className="h-6 w-6 rounded-full" />
          <Skeleton className="h-6 w-6 rounded-full" />
        </div>
      </div>
      {/* content */}
      <div className="flex-1 p-3">
        <ViewSkeleton />
      </div>
      {/* status bar */}
      <div className="flex h-6 items-center gap-4 border-t border-border bg-card px-3">
        <Skeleton className="h-2.5 w-20" />
        <Skeleton className="h-2.5 w-16" />
        <Skeleton className="ml-auto h-2.5 w-28" />
      </div>
    </div>
  );
}

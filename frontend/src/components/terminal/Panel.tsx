import { ReactNode } from "react";
import { cn } from "@/lib/utils";

/** The workspace's structural unit: a 1px-bordered panel whose uppercase mono
 *  micro-title says what the data inside IS (never decoration). */
export function Panel({
  title,
  right,
  children,
  className,
  bodyClassName,
  tourId,
}: {
  title: string;
  right?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
  /** Anchor for the guided tour's spotlight. */
  tourId?: string;
}) {
  return (
    <section data-tour={tourId} className={cn("border border-border bg-card", className)}>
      <header className="flex h-8 items-center justify-between border-b border-border bg-secondary/40 px-3">
        <h2 className="micro text-primary/90">{title}</h2>
        {right && <div className="flex items-center gap-2">{right}</div>}
      </header>
      <div className={cn("p-3", bodyClassName)}>{children}</div>
    </section>
  );
}

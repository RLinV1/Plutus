import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import type { UniverseItem } from "../types";
import { cn } from "@/lib/utils";

/** Form-friendly ticker combobox: type to search the universe (or any symbol),
 *  pick a match, and the chosen ticker STAYS in the field (unlike SearchBar,
 *  which clears after navigation). */
export function TickerInput({
  value,
  onChange,
  placeholder = "Ticker",
  className,
  ariaLabel = "Ticker",
  options,
}: {
  value: string;
  onChange: (symbol: string) => void;
  placeholder?: string;
  className?: string;
  ariaLabel?: string;
  /** When set, search ONLY these (e.g. current holdings for a sell) instead
   *  of the whole universe — and show them all on focus. */
  options?: UniverseItem[];
}) {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const boxRef = useRef<HTMLDivElement>(null);
  const { data: universe = [] } = useQuery({
    queryKey: ["universe"],
    queryFn: api.universe,
    staleTime: Infinity,
  });
  const pool = options ?? universe;

  const matches = useMemo(() => {
    const q = value.trim().toLowerCase();
    if (!q) return options ? options.slice(0, 8) : [];
    const rank = (u: UniverseItem): number => {
      const sym = u.symbol.toLowerCase();
      const name = u.name.toLowerCase();
      if (sym === q) return 0;
      if (sym.startsWith(q)) return 1;
      if (name.startsWith(q)) return 2;
      if (name.split(/[\s().&-]+/).some((w) => w.startsWith(q))) return 3;
      if (name.includes(q)) return 4;
      return 99;
    };
    return pool
      .map((u) => ({ u, r: rank(u) }))
      .filter((x) => x.r < 99)
      .sort((a, b) => a.r - b.r || a.u.symbol.localeCompare(b.u.symbol))
      .slice(0, 8)
      .map((x) => x.u);
  }, [value, pool, options]);

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  const choose = (symbol: string) => {
    onChange(symbol.toUpperCase());
    setOpen(false);
    setActive(0);
  };

  return (
    <div className={cn("relative", className)} ref={boxRef}>
      <input
        aria-label={ariaLabel}
        value={value}
        placeholder={placeholder}
        onChange={(e) => {
          onChange(e.target.value.toUpperCase());
          setOpen(true);
          setActive(0);
        }}
        onFocus={() => (value || options) && setOpen(true)}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") {
            e.preventDefault();
            setActive((a) => Math.min(a + 1, matches.length - 1));
          } else if (e.key === "ArrowUp") {
            e.preventDefault();
            setActive((a) => Math.max(a - 1, 0));
          } else if (e.key === "Enter" && open && matches[active]) {
            e.preventDefault();
            choose(matches[active].symbol);
          } else if (e.key === "Escape") {
            setOpen(false);
          }
        }}
        className="h-9 w-full border border-input bg-background px-2 font-mono text-sm uppercase outline-none placeholder:normal-case placeholder:text-muted-foreground focus-visible:ring-1 focus-visible:ring-ring"
      />
      {open && matches.length > 0 && (
        <ul className="absolute z-30 mt-1 w-64 max-w-[80vw] overflow-hidden border border-border bg-popover shadow-2xl">
          {matches.map((m, i) => (
            <li
              key={m.symbol}
              className={cn(
                "flex cursor-pointer items-baseline gap-2 px-2 py-1.5 text-xs",
                i === active && "bg-primary/15",
              )}
              onMouseEnter={() => setActive(i)}
              onMouseDown={(e) => {
                e.preventDefault();
                choose(m.symbol);
              }}
            >
              <span className="w-14 font-mono font-bold">{m.symbol}</span>
              <span className="truncate text-muted-foreground">{m.name}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

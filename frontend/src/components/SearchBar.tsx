import { useEffect, useMemo, useRef, useState } from "react";
import type { UniverseItem } from "../types";
import { cn } from "@/lib/utils";

interface Props {
  universe: UniverseItem[];
  onSelect: (symbol: string) => void;
  placeholder?: string;
  autoFocus?: boolean;
}

/** Type-to-search combobox: filters the known universe, and also accepts any
 *  ticker the user types that isn't in the list. */
export function SearchBar({ universe, onSelect, placeholder, autoFocus }: Props) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const boxRef = useRef<HTMLDivElement>(null);

  const matches = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return universe.slice(0, 8);
    // Rank by relevance so prefix matches win: a ticker symbol starting with the
    // query comes first (typing "D" → DASH, DELL, DIS…), then name-word prefixes,
    // then looser "contains" matches.
    const rank = (u: UniverseItem): number => {
      const sym = u.symbol.toLowerCase();
      const name = u.name.toLowerCase();
      if (sym.startsWith(q)) return 0;
      if (name.startsWith(q)) return 1;
      if (name.split(/[\s().&-]+/).some((w) => w.startsWith(q))) return 2;
      if (sym.includes(q)) return 3;
      if (name.includes(q)) return 4;
      return 99;
    };
    return universe
      .map((u) => ({ u, r: rank(u) }))
      .filter((x) => x.r < 99)
      .sort((a, b) => a.r - b.r || a.u.symbol.localeCompare(b.u.symbol))
      .slice(0, 8)
      .map((x) => x.u);
  }, [query, universe]);

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node))
        setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  const choose = (symbol: string) => {
    onSelect(symbol.toUpperCase());
    setQuery("");
    setOpen(false);
    setActive(0);
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((a) => Math.min(a + 1, matches.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => Math.max(a - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (matches[active]) choose(matches[active].symbol);
      else if (query.trim()) choose(query.trim());
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  };

  return (
    <div className="relative" ref={boxRef}>
      <svg
        className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
        viewBox="0 0 24 24"
        aria-hidden="true"
      >
        <path
          d="M21 21l-4.3-4.3M11 19a8 8 0 100-16 8 8 0 000 16z"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
        />
      </svg>
      <input
        className="h-12 w-full rounded-xl border border-input bg-card pl-10 pr-4 text-sm outline-none transition focus-visible:ring-2 focus-visible:ring-ring"
        value={query}
        autoFocus={autoFocus}
        placeholder={placeholder ?? "Search a company or ticker…"}
        onChange={(e) => {
          setQuery(e.target.value);
          setOpen(true);
          setActive(0);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={onKeyDown}
      />
      {open && matches.length > 0 && (
        <ul className="absolute z-30 mt-2 w-full overflow-hidden rounded-xl border border-border bg-popover p-1 shadow-2xl">
          {matches.map((m, i) => (
            <li
              key={m.symbol}
              className={cn(
                "flex cursor-pointer items-baseline gap-3 rounded-lg px-3 py-2",
                i === active && "bg-accent"
              )}
              onMouseEnter={() => setActive(i)}
              onMouseDown={(e) => {
                e.preventDefault();
                choose(m.symbol);
              }}
            >
              <span className="w-14 font-bold">{m.symbol}</span>
              <span className="truncate text-[0.8125rem] text-muted-foreground">
                {m.name}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

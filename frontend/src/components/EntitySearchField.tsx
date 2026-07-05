/**
 * EntitySearchField — generic debounced search-and-select field for picking
 * an entity by name instead of typing a numeric id.
 *
 * Mirrors the debounce/select pattern in
 * rituals/components/fields/CharacterSearchField.tsx, decoupled from that
 * file's FieldProps so it's usable outside rituals' dynamic forms (#882).
 */
import type { ChangeEvent } from 'react';
import { useEffect, useId, useRef, useState } from 'react';

import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

export interface EntitySearchResult {
  id: number;
  name: string;
  hint?: string;
}

interface EntitySearchFieldProps {
  value: number | null;
  onChange: (id: number | null) => void;
  search: (query: string) => Promise<EntitySearchResult[]>;
  resolveById?: (id: number) => Promise<EntitySearchResult | null>;
  label: string;
  placeholder?: string;
  disabled?: boolean;
}

export function EntitySearchField({
  value,
  onChange,
  search,
  resolveById,
  label,
  placeholder,
  disabled,
}: EntitySearchFieldProps) {
  const id = useId();
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<EntitySearchResult[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [searching, setSearching] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Keep the latest callbacks without re-triggering the effects below —
  // callers commonly pass new closures every render.
  const searchRef = useRef(search);
  searchRef.current = search;
  const resolveRef = useRef(resolveById);
  resolveRef.current = resolveById;

  // Resolve an externally-set value's display name (e.g. on mount).
  // Note: selectedId is intentionally not in the dependency array — we only
  // want this effect to run when the external `value` prop changes, not when
  // selectedId changes from internal user actions (e.g. clicking a search
  // result). Both branches below still read the latest selectedId from the
  // closure to guard against redundant resets when the effect does run.
  useEffect(() => {
    if (value === null) {
      if (selectedId === null) return;
      setSelectedId(null);
      setQuery('');
      return;
    }
    if (value === selectedId) return;
    setSelectedId(value);
    if (!resolveRef.current) {
      setQuery(String(value));
      return;
    }
    let cancelled = false;
    resolveRef
      .current(value)
      .then((entity) => {
        if (!cancelled) setQuery(entity ? entity.name : String(value));
      })
      .catch(() => {
        if (!cancelled) setQuery(String(value));
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);

  // Debounced search as the user types.
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (query.trim().length < 2) {
      setResults([]);
      return;
    }
    debounceRef.current = setTimeout(() => {
      setSearching(true);
      searchRef
        .current(query.trim())
        .then(setResults)
        .catch(() => setResults([]))
        .finally(() => setSearching(false));
    }, 300);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [query]);

  function handleSelect(entity: EntitySearchResult) {
    setSelectedId(entity.id);
    setQuery(entity.name);
    setResults([]);
    onChange(entity.id);
  }

  function handleInputChange(e: ChangeEvent<HTMLInputElement>) {
    const next = e.target.value;
    setQuery(next);
    if (selectedId !== null) {
      setSelectedId(null);
      onChange(null);
    }
  }

  return (
    <div className="space-y-1">
      <Label htmlFor={id}>{label}</Label>
      <div className="relative">
        <Input
          id={id}
          value={query}
          onChange={handleInputChange}
          placeholder={placeholder}
          autoComplete="off"
          disabled={disabled}
        />
        {searching && (
          <span className="absolute right-2 top-2 text-xs text-muted-foreground">Searching…</span>
        )}
        {results.length > 0 && (
          <ul className="absolute z-50 mt-1 max-h-48 w-full overflow-auto rounded-md border bg-popover shadow-lg">
            {results.map((r) => (
              <li key={r.id}>
                <button
                  type="button"
                  className="w-full px-3 py-2 text-left text-sm hover:bg-accent"
                  onClick={() => handleSelect(r)}
                >
                  {r.name}
                  {r.hint ? <span className="text-muted-foreground"> — {r.hint}</span> : null}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

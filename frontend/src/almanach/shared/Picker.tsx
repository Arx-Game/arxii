/**
 * Picker (#4239): search as you type over the Almanach's search route, narrowed
 * to one kind, with Create offered in place when nothing (or nothing right)
 * comes back. Every slot on a page is one of these.
 */
import { useId, useState } from 'react';

import { useSearch } from '../queries';
import type { SearchHit } from '../types';

export interface PickerProps {
  kind: SearchHit['kind'];
  placeholder: string;
  onPick: (hit: SearchHit) => void;
  /** The Create affordance's label, e.g. "Create Family"; omitted hides it. */
  createLabel?: string;
  onCreate?: (typed: string) => void;
  /** Hit ids to leave out (the person themself, the house already picked). */
  exclude?: number[];
  ariaLabel?: string;
}

export function Picker({
  kind,
  placeholder,
  onPick,
  createLabel,
  onCreate,
  exclude = [],
  ariaLabel,
}: PickerProps) {
  const [q, setQ] = useState('');
  const listId = useId();
  const { data } = useSearch(q);
  const hits = (data ?? []).filter((h) => h.kind === kind && !exclude.includes(h.id));
  const searching = q.trim().length >= 2;
  return (
    <div className="pick" role="group" aria-label={ariaLabel ?? placeholder}>
      <input
        type="search"
        className="rs"
        placeholder={placeholder}
        value={q}
        aria-controls={listId}
        onChange={(e) => setQ(e.target.value)}
      />
      {searching && (
        <ul id={listId} className="hits">
          {hits.map((hit) => (
            <li key={`${hit.kind}-${hit.id}`}>
              <button
                type="button"
                onClick={() => {
                  setQ('');
                  onPick(hit);
                }}
              >
                {hit.name}
                {hit.sub && <small> {hit.sub}</small>}
              </button>
            </li>
          ))}
          {hits.length === 0 && <li className="meta">none found</li>}
          {createLabel && onCreate && (
            <li>
              <button type="button" className="new" onClick={() => onCreate(q.trim())}>
                {createLabel}
              </button>
            </li>
          )}
        </ul>
      )}
      {!searching && createLabel && onCreate && (
        <button type="button" className="new" onClick={() => onCreate('')}>
          {createLabel}
        </button>
      )}
    </div>
  );
}

/**
 * FolioCrumb (#3477 Task 4) — the Atlas's sticky folio-line: the ancestor
 * chain rendered as the Commonplace Book idiom's crumb, one clickable button
 * per ancestor and the current node set bold and inert. Mirrors
 * `world.areas.builder_views._area_breadcrumb`'s shape exactly (outermost
 * ancestor first, the CURRENT node last — see its docstring): this component
 * never re-orders or trims the list, just renders it.
 *
 * Each entry carries its own small level tag (the prototype's `.lvl`
 * treatment) via `PlateHead` — sized down for an inline badge rather than a
 * full section label, but the same small-caps/tracked/muted primitive
 * everywhere else in the Atlas uses for this kind of tag (#3477 fix round 1).
 *
 * Between two entries an area level can still fit (a city straight above a
 * room, say), the separator carries an insert point (2026-09-09, the reviewer
 * editing City Center under Arx: "being able to click between them and add a
 * level in between would be really nice"). The crumb only decides *where* a
 * level fits (`insertableLevels`); the caller owns the dialog and the chain of
 * dispatches that creates the level and moves the lower node inside it.
 */
import { Fragment, type ReactNode } from 'react';

import { PlateHead } from '@/components/folio';
import { insertableLevels } from './constants';

export interface FolioCrumbEntry {
  id: number;
  name: string;
  level_display?: string;
  /** Numeric `AreaLevel` for an area entry; a room entry carries none (`kind: 'room'`). */
  level?: number;
  /** Defaults to `'area'`; the room document's own crumb ends in a `'room'` entry. */
  kind?: 'area' | 'room';
}

export interface FolioCrumbProps {
  /** Outermost ancestor first; the LAST entry is the current node (bold, inert). */
  entries: FolioCrumbEntry[];
  onSelect: (id: number) => void;
  /** When given, a ⊕ appears between two entries a level can fit between; fires with that pair. */
  onInsertBetween?: (upper: FolioCrumbEntry, lower: FolioCrumbEntry) => void;
  /** Right-aligned folio-line controls (search, pin, …) — owned by the caller. */
  children?: ReactNode;
}

function LevelTag({ level }: { level?: string }) {
  if (!level) return null;
  return (
    <PlateHead
      as="span"
      className="ml-1.5 text-[0.6rem] tracking-[0.12em]"
      data-testid="folio-crumb-level"
    >
      {level}
    </PlateHead>
  );
}

export function FolioCrumb({ entries, onSelect, onInsertBetween, children }: FolioCrumbProps) {
  const lastIndex = entries.length - 1;
  const insertPoint = (index: number) => {
    if (!onInsertBetween) return null;
    const upper = entries[index];
    const lower = entries[index + 1];
    if (insertableLevels(upper, lower).length === 0) return null;
    return (
      <button
        type="button"
        className="px-0.5 text-muted-foreground hover:text-primary"
        aria-label={`add a level between ${upper.name} and ${lower.name}`}
        title={`add a level between ${upper.name} and ${lower.name}`}
        onClick={() => onInsertBetween(upper, lower)}
        data-testid="folio-crumb-insert"
      >
        ⊕
      </button>
    );
  };
  return (
    <div
      className="sticky top-0 z-10 flex items-baseline gap-2 border-b bg-background px-4 py-2 font-body text-sm text-muted-foreground"
      data-testid="folio-crumb"
    >
      <span className="flex flex-wrap items-baseline gap-1">
        {entries.map((entry, index) =>
          index === lastIndex ? (
            <span key={entry.id} className="flex items-baseline">
              <b className="font-medium text-foreground" data-testid="folio-crumb-current">
                {entry.name}
              </b>
              <LevelTag level={entry.level_display} />
            </span>
          ) : (
            <Fragment key={entry.id}>
              <span className="flex items-baseline">
                <button
                  type="button"
                  className="hover:text-primary"
                  onClick={() => onSelect(entry.id)}
                  data-testid="folio-crumb-ancestor"
                >
                  {entry.name}
                </button>
                <LevelTag level={entry.level_display} />
              </span>
              <span aria-hidden="true" className="opacity-60">
                ❯
              </span>
              {insertPoint(index)}
            </Fragment>
          )
        )}
      </span>
      {children && <div className="ml-auto flex items-center gap-4">{children}</div>}
    </div>
  );
}

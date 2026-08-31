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
 */
import { Fragment, type ReactNode } from 'react';

import { PlateHead } from '@/components/folio';

export interface FolioCrumbEntry {
  id: number;
  name: string;
  level_display?: string;
}

export interface FolioCrumbProps {
  /** Outermost ancestor first; the LAST entry is the current node (bold, inert). */
  entries: FolioCrumbEntry[];
  onSelect: (id: number) => void;
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

export function FolioCrumb({ entries, onSelect, children }: FolioCrumbProps) {
  const lastIndex = entries.length - 1;
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
            </Fragment>
          )
        )}
      </span>
      {children && <div className="ml-auto flex items-center gap-4">{children}</div>}
    </div>
  );
}

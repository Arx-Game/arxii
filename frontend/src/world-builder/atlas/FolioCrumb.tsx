/**
 * FolioCrumb (#3477 Task 4) — the Atlas's sticky folio-line: the ancestor
 * chain rendered as the Commonplace Book idiom's crumb, one clickable button
 * per ancestor and the current node set bold and inert. Mirrors
 * `world.areas.builder_views._area_breadcrumb`'s shape exactly (outermost
 * ancestor first, the CURRENT node last — see its docstring): this component
 * never re-orders or trims the list, just renders it.
 */
import { Fragment, type ReactNode } from 'react';

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
            <b
              key={entry.id}
              className="font-medium text-foreground"
              data-testid="folio-crumb-current"
            >
              {entry.name}
            </b>
          ) : (
            <Fragment key={entry.id}>
              <button
                type="button"
                className="hover:text-primary"
                onClick={() => onSelect(entry.id)}
                data-testid="folio-crumb-ancestor"
              >
                {entry.name}
              </button>
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

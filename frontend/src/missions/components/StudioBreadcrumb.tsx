/**
 * Studio breadcrumb — shared across NodePage / OptionPage / GiverEditor.
 *
 * Renders a row of links separated by `›` for the drill-down path. The
 * first crumb always links back to the browser; trailing crumbs are
 * plain text (the current page).
 */

import { Link } from 'react-router-dom';

export interface BreadcrumbCrumb {
  label: string;
  to?: string;
}

export function StudioBreadcrumb({ crumbs }: { crumbs: readonly BreadcrumbCrumb[] }) {
  return (
    <nav
      aria-label="Breadcrumb"
      className="flex flex-wrap items-center gap-1 text-sm text-muted-foreground"
      data-testid="studio-breadcrumb"
    >
      {crumbs.map((c, i) => {
        const isLast = i === crumbs.length - 1;
        return (
          <span key={`${c.label}-${i}`} className="flex items-center gap-1">
            {c.to && !isLast ? (
              <Link to={c.to} className="hover:underline">
                {c.label}
              </Link>
            ) : (
              <span className={isLast ? 'font-medium text-foreground' : undefined}>{c.label}</span>
            )}
            {!isLast ? <span aria-hidden>›</span> : null}
          </span>
        );
      })}
    </nav>
  );
}

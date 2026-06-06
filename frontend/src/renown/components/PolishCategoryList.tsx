import type { CategoryPolish } from '../types';

interface Props {
  rows: CategoryPolish[];
}

/**
 * Per-category polish breakdown rendered inside `OwnedDwellingsCard` and
 * `TenantedRoomsCard`. Shows tier label + category name on the left,
 * mono-formatted numeric value on the right; falls back to a muted
 * "no polish recorded" line when the row list is empty.
 */
export function PolishCategoryList({ rows }: Props) {
  if (rows.length === 0) {
    return <p className="mt-1 text-xs text-muted-foreground">No polish recorded yet.</p>;
  }
  return (
    <ul className="mt-2 space-y-1 text-xs">
      {rows.map((row) => (
        <li key={row.category_id} className="flex items-baseline justify-between gap-2">
          <span>
            {row.tier_label !== null && <span className="mr-1 font-medium">{row.tier_label}</span>}
            <span className="text-muted-foreground">{row.category_name}</span>
          </span>
          <span className="font-mono text-foreground">{row.value.toLocaleString()}</span>
        </li>
      ))}
    </ul>
  );
}

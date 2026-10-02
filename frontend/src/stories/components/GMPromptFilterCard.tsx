/**
 * GMPromptFilterCard — "GM settings · narration prompts" (#4101, demo Screen 5).
 *
 * One row per `GMPromptGroup` (always exactly five, server-synthesized) with
 * a "Prompt me" checkbox, plus a fixed final "Player actions" row with no
 * checkbox — players always write their own lines; a GM is never prompted
 * for those.
 *
 * Demo-fidelity fix round (F7): rows are divider-separated (the demo's
 * `.admin-field` border-bottom), the checkbox sits before its "Prompt me"
 * label (the demo's "☑ Prompt me"), and the checkbox's accent colour comes
 * from the theme's `--primary` token (`accent-primary`, the repo's
 * established checkbox pattern -- see `CategoryMultiSelect.tsx`) instead of
 * the browser default blue. Each checkbox keeps its own distinct accessible
 * name via `aria-label`.
 *
 * Demo-fidelity fix round 2 (F7b): rows are a label/value grid
 * (`.admin-field`'s `minmax(8rem, 10rem) 1fr` column pair), not
 * `justify-between` -- "☑ Prompt me" sits right after the label column
 * instead of pinned to the row's far-right edge.
 *
 * #4101 final review: group labels are small and muted (F7c, the demo's
 * label column), so "Audere / Audere Majora" stays on one line in the 160px
 * column and every row is the same height; checkboxes are disabled while a
 * save is in flight (F8), so a second click cannot race the first.
 */
import {
  useGMPromptFilters,
  useSetGMPromptFilter,
  type GMPromptFilterRow,
} from '@/scenes/gmPromptQueries';
import { Skeleton } from '@/components/ui/skeleton';

export function GMPromptFilterCard() {
  const { data: rows, isLoading, isError, error } = useGMPromptFilters();
  const setFilter = useSetGMPromptFilter();

  return (
    <section className="rounded-lg border p-4" aria-labelledby="gm-prompt-filter-heading">
      <h2 id="gm-prompt-filter-heading" className="mb-2 text-lg font-semibold">
        GM settings · narration prompts
      </h2>
      {isLoading && <Skeleton className="h-24 w-full" />}
      {isError && (
        <p role="alert" className="text-sm text-destructive">
          {(error as Error).message}
        </p>
      )}
      {rows && (
        <ul className="divide-y divide-border text-sm">
          {rows.map((row) => (
            <FilterRow
              key={row.group}
              row={row}
              onToggle={setFilter.mutate}
              saving={setFilter.isPending}
            />
          ))}
          <li className="grid grid-cols-[minmax(8rem,10rem)_1fr] items-center gap-2 py-2 text-muted-foreground">
            <span className="text-xs text-muted-foreground">Player actions</span>
            <span className="italic">Never prompt. Players write their own.</span>
          </li>
        </ul>
      )}
      {setFilter.isError && (
        <p role="alert" className="mt-2 text-sm text-destructive">
          {(setFilter.error as Error).message}
        </p>
      )}
    </section>
  );
}

function FilterRow({
  row,
  onToggle,
  saving,
}: {
  row: GMPromptFilterRow;
  onToggle: (body: { group: string; enabled: boolean }) => void;
  saving: boolean;
}) {
  return (
    <li className="grid grid-cols-[minmax(8rem,10rem)_1fr] items-center gap-2 py-2">
      <span className="text-xs text-muted-foreground">{row.label}</span>
      <label className="flex items-center gap-2">
        <input
          type="checkbox"
          checked={row.enabled}
          disabled={saving}
          onChange={() => onToggle({ group: row.group, enabled: !row.enabled })}
          aria-label={`Prompt me: ${row.label}`}
          className="h-4 w-4 rounded border-border accent-primary"
        />
        Prompt me
      </label>
    </li>
  );
}

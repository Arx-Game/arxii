/**
 * GMPromptFilterCard — "GM settings · narration prompts" (#4101, demo Screen 5).
 *
 * One row per `GMPromptGroup` (always exactly five, server-synthesized) with
 * a "Prompt me" checkbox, plus a fixed final "Player actions" row with no
 * checkbox — players always write their own lines; a GM is never prompted
 * for those.
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
        <ul className="space-y-2 text-sm">
          {rows.map((row) => (
            <FilterRow key={row.group} row={row} onToggle={setFilter.mutate} />
          ))}
          <li className="flex items-center justify-between gap-2 text-muted-foreground">
            <span>Player actions</span>
            <span className="text-xs">Never prompt. Players write their own.</span>
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
}: {
  row: GMPromptFilterRow;
  onToggle: (body: { group: string; enabled: boolean }) => void;
}) {
  return (
    <li className="flex items-center justify-between gap-2">
      <span>{row.label}</span>
      <label className="flex items-center gap-2">
        Prompt me
        <input
          type="checkbox"
          checked={row.enabled}
          onChange={() => onToggle({ group: row.group, enabled: !row.enabled })}
        />
      </label>
    </li>
  );
}

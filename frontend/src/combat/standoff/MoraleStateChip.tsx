/**
 * Faltering / Broken chip (#4147). The derived morale state is observable to every
 * viewer; the morale number stays GM-only and is never passed here.
 */

export function MoraleStateChip({ state }: { state: string | null | undefined }) {
  if (state === 'falter') {
    return (
      <span
        data-testid="morale-state-chip"
        className="shrink-0 rounded bg-amber-500/15 px-1 py-0.5 text-[10px] text-amber-700 dark:text-amber-300"
      >
        Faltering
      </span>
    );
  }
  if (state === 'break') {
    return (
      <span
        data-testid="morale-state-chip"
        className="shrink-0 rounded bg-destructive/15 px-1 py-0.5 text-[10px] text-destructive"
      >
        Broken
      </span>
    );
  }
  return null;
}

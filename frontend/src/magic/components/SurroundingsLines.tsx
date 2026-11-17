/**
 * The lines a cast card shows under its cost about where she stands (#5018, #5125): calling
 * up her gift's substance (free, or what it costs), a heading over each source of Primum
 * with its points, the power they add, and any surroundings a technique needs that the room
 * lacks. Server-written text; this only colours it.
 */
import { cn } from '@/lib/utils';
import type { SurroundingsLine } from '@/scenes/actionTypes';

function amountText(line: SurroundingsLine): string {
  if (line.kind === 'power') {
    return `${line.amount > 0 ? '+' : ''}${line.amount} power`;
  }
  if (line.kind === 'source') {
    return String(line.amount);
  }
  return line.detail ?? '';
}

function toneFor(line: SurroundingsLine): string {
  if (line.kind === 'power') {
    return line.amount >= 0
      ? 'text-emerald-600 dark:text-emerald-400'
      : 'text-amber-700 dark:text-amber-400';
  }
  if (line.kind === 'source') {
    return line.amount < 0 ? 'text-amber-700 dark:text-amber-400' : '';
  }
  if (line.kind === 'call_up') {
    return line.anima === 0
      ? 'text-sky-600 dark:text-sky-400'
      : 'text-amber-700 dark:text-amber-400';
  }
  if (line.kind === 'needs') {
    return 'text-red-600 dark:text-red-400';
  }
  if (line.kind === 'blocked') {
    return 'text-amber-700 dark:text-amber-400';
  }
  return 'text-muted-foreground';
}

/**
 * Each line with a key from its kind and text, with a count of the earlier lines that share
 * both, so two identical lines stay distinct without the position being the identity.
 */
function keyedLines(lines: SurroundingsLine[]): { key: string; line: SurroundingsLine }[] {
  const seen = new Map<string, number>();
  return lines.map((line) => {
    const base = `${line.kind}:${line.text}`;
    const count = seen.get(base) ?? 0;
    seen.set(base, count + 1);
    return { key: `${base}:${count}`, line };
  });
}

export function SurroundingsLines({ lines }: { lines: SurroundingsLine[] }) {
  if (lines.length === 0) {
    return null;
  }
  // A heading or source can repeat text, so a repeat is told apart by how many came before.
  const keyed = keyedLines(lines);
  return (
    <ul className="space-y-0.5 text-xs" data-testid="surroundings-lines">
      {keyed.map(({ key, line }) =>
        line.kind === 'heading' ? (
          <li
            key={key}
            className="pt-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground"
          >
            {line.text}
          </li>
        ) : (
          <li key={key} className="flex justify-between gap-2">
            <span className={cn('min-w-0', toneFor(line))}>{line.text}</span>
            {amountText(line) && (
              <span
                className={cn(
                  'text-right',
                  line.kind === 'power' || line.kind === 'source' ? 'shrink-0' : 'basis-1/2',
                  (line.kind === 'power' || line.kind === 'source') && 'font-mono',
                  toneFor(line)
                )}
              >
                {amountText(line)}
              </span>
            )}
          </li>
        )
      )}
    </ul>
  );
}

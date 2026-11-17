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

export function SurroundingsLines({ lines }: { lines: SurroundingsLine[] }) {
  if (lines.length === 0) {
    return null;
  }
  // The server sends the lines in order and a heading or source can repeat text, so the
  // position is the identity.
  return (
    <ul className="space-y-0.5 text-xs" data-testid="surroundings-lines">
      {lines.map((line, index) =>
        line.kind === 'heading' ? (
          <li
            key={index}
            className="pt-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground"
          >
            {line.text}
          </li>
        ) : (
          <li key={index} className="flex justify-between gap-2">
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

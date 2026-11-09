/**
 * The lines a cast card shows under its cost about where she stands (#5018): calling up
 * her gift's substance (free, or what it costs), the power the room gives or takes, and
 * any surroundings a technique needs that the room lacks. Server-written text; this only
 * colours it.
 */
import { cn } from '@/lib/utils';
import type { SurroundingsLine } from '@/scenes/actionTypes';

function amountText(line: SurroundingsLine): string {
  if (line.kind === 'power') {
    return `${line.amount > 0 ? '+' : ''}${line.amount} power`;
  }
  return '';
}

function toneFor(line: SurroundingsLine): string {
  if (line.kind === 'power') {
    return line.amount >= 0
      ? 'text-emerald-600 dark:text-emerald-400'
      : 'text-red-600 dark:text-red-400';
  }
  if (line.kind === 'call_up') {
    return line.anima === 0 && line.resonance === 0
      ? 'text-sky-600 dark:text-sky-400'
      : 'text-amber-700 dark:text-amber-400';
  }
  if (line.kind === 'needs') {
    return 'text-red-600 dark:text-red-400';
  }
  return 'text-muted-foreground';
}

export function SurroundingsLines({ lines }: { lines: SurroundingsLine[] }) {
  if (lines.length === 0) {
    return null;
  }
  return (
    <ul className="space-y-0.5 text-xs" data-testid="surroundings-lines">
      {lines.map((line) => (
        <li key={`${line.kind}-${line.text}`} className="flex justify-between gap-2">
          <span className={cn(toneFor(line))}>{line.text}</span>
          {amountText(line) && (
            <span className={cn('font-mono', toneFor(line))}>{amountText(line)}</span>
          )}
        </li>
      ))}
    </ul>
  );
}

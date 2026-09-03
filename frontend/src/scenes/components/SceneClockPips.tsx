import { cn } from '@/lib/utils';

interface Props {
  size: number;
  filled: number;
  className?: string;
}

/**
 * Scene clock (#3567): one pip per tick, filled pips first. The fairness
 * mechanism is that everyone sees it; it names no beat and no consequence.
 */
export function SceneClockPips({ size, filled, className }: Props) {
  const pips = Array.from({ length: size }, (_, i) => i < filled);
  return (
    <div
      className={cn('inline-flex items-center gap-1', className)}
      role="img"
      aria-label={`Clock ${filled} of ${size}`}
      title={`Clock ${filled} of ${size}`}
      data-testid="scene-clock"
    >
      {pips.map((isFilled, i) => (
        <span
          key={i}
          data-testid={isFilled ? 'scene-clock-pip-filled' : 'scene-clock-pip-empty'}
          className={cn(
            'h-2.5 w-2.5 rounded-full border border-foreground/60',
            isFilled ? 'bg-foreground/80' : 'bg-transparent'
          )}
        />
      ))}
      <span className="ml-1 text-xs text-muted-foreground">
        {filled}/{size}
      </span>
    </div>
  );
}

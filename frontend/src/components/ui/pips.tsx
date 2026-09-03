import { cn } from '@/lib/utils';

export interface PipsProps {
  filled: number;
  total: number;
  label: string;
  tone?: 'neutral' | 'success' | 'failure';
  testId?: string;
  className?: string;
}

const TONE: Record<NonNullable<PipsProps['tone']>, string> = {
  neutral: 'bg-foreground/80 border-foreground/60',
  success: 'bg-emerald-600 border-emerald-700',
  failure: 'bg-red-600 border-red-700',
};

/** A row of N pips with the first `filled` marked; counts only, no names (#3568). */
export function Pips({
  filled,
  total,
  label,
  tone = 'neutral',
  testId = 'pips',
  className,
}: PipsProps) {
  const pips = Array.from({ length: total }, (_, i) => i < filled);
  return (
    <div
      className={cn('inline-flex items-center gap-1', className)}
      role="img"
      aria-label={`${label} ${filled} of ${total}`}
      title={`${label} ${filled} of ${total}`}
      data-testid={testId}
    >
      {pips.map((isFilled, i) => (
        <span
          key={i}
          data-testid={isFilled ? `${testId}-filled` : `${testId}-empty`}
          className={cn(
            'h-2.5 w-2.5 rounded-full border',
            isFilled ? TONE[tone] : 'border-foreground/40 bg-transparent'
          )}
        />
      ))}
      <span className="ml-1 text-xs text-muted-foreground">
        {filled}/{total}
      </span>
    </div>
  );
}

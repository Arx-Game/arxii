import type { ReactNode } from 'react';
import { Progress } from '@/components/ui/progress';

export interface StatBarProps {
  label: string;
  /** Right-aligned numerals, e.g. "40/100". */
  valueText: string;
  /** Fill percentage 0-100 (already inverted/clamped by the caller if needed). */
  percent: number;
  /** Tailwind fill class for the Progress indicator. */
  fillClass: string;
  /** Optional element rendered beside the numerals (e.g. a zone Badge). */
  badge?: ReactNode;
  /** Optional muted note rendered under the bar (e.g. wound description). */
  note?: string;
  testId?: string;
}

export function StatBar({
  label,
  valueText,
  percent,
  fillClass,
  badge,
  note,
  testId,
}: StatBarProps) {
  const clamped = Math.max(0, Math.min(100, percent));
  return (
    <div className="space-y-1" data-testid={testId}>
      <div className="flex items-center justify-between text-sm">
        <span className="font-medium">{label}</span>
        <div className="flex items-center gap-2">
          <span className="tabular-nums text-muted-foreground">{valueText}</span>
          {badge}
        </div>
      </div>
      <Progress value={clamped} className="h-2" indicatorClassName={fillClass} aria-label={label} />
      {note && <p className="text-xs text-muted-foreground">{note}</p>}
    </div>
  );
}

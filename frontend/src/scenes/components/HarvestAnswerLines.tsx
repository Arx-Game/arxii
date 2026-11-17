/** The server's answer to a Harvest, kept on screen (#5125). */
import { cn } from '@/lib/utils';
import type { HarvestAnswer } from '../harvestAnswer';

export function HarvestAnswerLines({ answer }: { answer: HarvestAnswer }) {
  return (
    <div className="space-y-0.5 text-xs" data-testid="harvest-answer">
      <p className={cn('font-medium', !answer.success && 'text-amber-700 dark:text-amber-400')}>
        {answer.message}
      </p>
      {answer.remainingLine && <p className="text-muted-foreground">{answer.remainingLine}</p>}
    </div>
  );
}

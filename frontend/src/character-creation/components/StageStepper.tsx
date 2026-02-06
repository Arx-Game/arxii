/**
 * Stage Stepper component
 *
 * Horizontal breadcrumb showing progress through character creation stages.
 * All stages are clickable (free navigation), incomplete stages show warning badge.
 */

import { cn } from '@/lib/utils';
import { AlertCircle, CheckCircle2 } from 'lucide-react';
import { Stage, STAGE_LABELS } from '../types';

interface StageStepper {
  currentStage: Stage;
  stageCompletion: Record<Stage, boolean>;
  onStageSelect: (stage: Stage) => void;
}

const STAGES = [
  Stage.ORIGIN,
  Stage.HERITAGE,
  Stage.LINEAGE,
  Stage.DISTINCTIONS,
  Stage.PATH_SKILLS,
  Stage.ATTRIBUTES,
  Stage.MAGIC,
  Stage.APPEARANCE,
  Stage.IDENTITY,
  Stage.FINAL_TOUCHES,
  Stage.REVIEW,
];

export function StageStepper({ currentStage, stageCompletion, onStageSelect }: StageStepper) {
  return (
    <nav aria-label="Character creation progress" className="mb-8">
      <ol className="flex flex-wrap items-center gap-2 md:gap-4">
        {STAGES.map((stage, index) => {
          const isComplete = stageCompletion[stage];
          const isCurrent = stage === currentStage;
          const isReview = stage === Stage.REVIEW;

          return (
            <li key={stage} className="flex items-center">
              {index > 0 && (
                <div
                  className={cn(
                    'mr-2 hidden h-px w-4 md:mr-4 md:block md:w-8',
                    isComplete || stageCompletion[STAGES[index - 1]]
                      ? 'bg-primary'
                      : 'bg-muted-foreground/30'
                  )}
                />
              )}
              <button
                onClick={() => onStageSelect(stage)}
                className={cn(
                  'group flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
                  isCurrent ? 'bg-primary text-primary-foreground' : 'hover:bg-muted',
                  !isCurrent && isComplete && 'text-primary',
                  !isCurrent && !isComplete && !isReview && 'text-muted-foreground'
                )}
              >
                <span className="flex h-6 w-6 items-center justify-center">
                  {isComplete && !isReview ? (
                    <CheckCircle2 className="h-5 w-5 text-green-500" />
                  ) : !isComplete && !isReview && stage < currentStage ? (
                    <AlertCircle className="h-5 w-5 text-yellow-500" />
                  ) : (
                    <span
                      className={cn(
                        'flex h-6 w-6 items-center justify-center rounded-full border-2 text-xs',
                        isCurrent
                          ? 'border-primary-foreground'
                          : isComplete
                            ? 'border-primary'
                            : 'border-muted-foreground/50'
                      )}
                    >
                      {index + 1}
                    </span>
                  )}
                </span>
                <span className="hidden sm:inline">{STAGE_LABELS[stage]}</span>
              </button>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

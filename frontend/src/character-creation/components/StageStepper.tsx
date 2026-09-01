/**
 * Stage Stepper component
 *
 * Horizontal breadcrumb showing progress through character creation stages.
 * All stages are clickable (free navigation), incomplete stages show warning badge.
 * Hovering over incomplete stages shows a tooltip with specific validation errors.
 */

import { HoverCard, HoverCardContent, HoverCardTrigger } from '@/components/ui/hover-card';
import { cn } from '@/lib/utils';
import { AlertCircle, CheckCircle2 } from 'lucide-react';
import { Stage, STAGE_LABELS } from '../types';

interface StageStepper {
  currentStage: Stage;
  stageCompletion: Record<Stage, boolean>;
  stageErrors: Partial<Record<Stage, string[]>>;
  onStageSelect: (stage: Stage) => void;
}

const STAGES = [
  Stage.ORIGIN,
  Stage.HERITAGE,
  Stage.LINEAGE,
  Stage.DISTINCTIONS,
  Stage.PATH,
  Stage.GIFT,
  Stage.ATTRIBUTES,
  Stage.APPEARANCE,
  Stage.IDENTITY,
  Stage.FINAL_TOUCHES,
  Stage.REVIEW,
];

/** The circle, check or warning badge that stands for one stage's state. */
function StageBadge({
  index,
  isComplete,
  isCurrent,
  isReview,
  isBehind,
}: {
  index: number;
  isComplete: boolean;
  isCurrent: boolean;
  isReview: boolean;
  isBehind: boolean;
}) {
  if (isComplete && !isReview) {
    return <CheckCircle2 className="h-5 w-5 text-green-500" />;
  }
  if (!isComplete && !isReview && isBehind) {
    return <AlertCircle className="h-5 w-5 text-yellow-500" />;
  }
  return (
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
  );
}

/** One stage in the breadcrumb: its connector, its button, and its error tooltip. */
function StageStep({
  stage,
  index,
  currentStage,
  stageCompletion,
  errors,
  onStageSelect,
}: {
  stage: Stage;
  index: number;
  currentStage: Stage;
  stageCompletion: Record<Stage, boolean>;
  errors: string[];
  onStageSelect: (stage: Stage) => void;
}) {
  const isComplete = stageCompletion[stage];
  const isCurrent = stage === currentStage;
  const isReview = stage === Stage.REVIEW;
  // Review is never flagged: it has nothing of its own to complete.
  const showTooltip = !isComplete && !isReview && errors.length > 0;

  const button = (
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
        <StageBadge
          index={index}
          isComplete={isComplete}
          isCurrent={isCurrent}
          isReview={isReview}
          isBehind={stage < currentStage}
        />
      </span>
      <span className="hidden sm:inline">{STAGE_LABELS[stage]}</span>
    </button>
  );

  return (
    <li className="flex items-center">
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
      {showTooltip ? (
        <HoverCard openDelay={200}>
          <HoverCardTrigger asChild>{button}</HoverCardTrigger>
          <HoverCardContent className="w-64">
            <p className="mb-1 text-xs font-semibold text-muted-foreground">
              {STAGE_LABELS[stage]}: incomplete
            </p>
            <ul className="list-disc pl-4 text-sm">
              {errors.map((error) => (
                <li key={error}>{error}</li>
              ))}
            </ul>
          </HoverCardContent>
        </HoverCard>
      ) : (
        button
      )}
    </li>
  );
}

export function StageStepper({
  currentStage,
  stageCompletion,
  stageErrors,
  onStageSelect,
}: StageStepper) {
  return (
    <nav aria-label="Character creation progress">
      <ol className="flex flex-wrap items-center gap-2 md:gap-4">
        {STAGES.map((stage, index) => (
          <StageStep
            key={stage}
            stage={stage}
            index={index}
            currentStage={currentStage}
            stageCompletion={stageCompletion}
            errors={stageErrors[stage] ?? []}
            onStageSelect={onStageSelect}
          />
        ))}
      </ol>
    </nav>
  );
}

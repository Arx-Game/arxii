/**
 * Shared reads of a draft's magical training (#4659), used by the Gift stage's funnel
 * step and the `MagicTrainingBlock` inside it.
 */

import type { CGExplanations, MagicTraining } from '../../types';

/** A draft has a training step when it has any pool or anything already allocated. */
export function hasMagicTraining(training: MagicTraining | undefined): boolean {
  return training != null && (training.total > 0 || training.allocated > 0);
}

/** The pool is settled when the allocation spends exactly what it must, and no more. */
export function isTrainingSpent(training: MagicTraining): boolean {
  return training.allocated === training.required_spend && training.allocated <= training.total;
}

/** "What {tradition} taught you", through its copy key. */
export function trainingHeading(copy: CGExplanations | undefined, traditionName: string): string {
  return (copy?.gift_training_heading ?? 'What {tradition} taught you').replace(
    '{tradition}',
    traditionName
  );
}

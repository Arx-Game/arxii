/**
 * The contents rail (#3540): progress as a table of contents, never a stepper.
 * The ten stages with complete / current / not-yet-started state, the
 * validation reason as an "n.b." note, and the restart door beneath. Free
 * navigation is preserved (every stage is a link). Replaces StageStepper.
 */

import type { ReactNode } from 'react';
import { Stage, STAGE_LABELS } from '../types';

export const CHAPTERS: ReadonlyArray<{ stage: Stage }> = [
  { stage: Stage.ORIGIN },
  { stage: Stage.HERITAGE },
  { stage: Stage.LINEAGE },
  { stage: Stage.PATH },
  { stage: Stage.GIFT },
  { stage: Stage.ATTRIBUTES },
  { stage: Stage.APPEARANCE },
  { stage: Stage.IDENTITY },
  { stage: Stage.FINAL_TOUCHES },
  { stage: Stage.REVIEW },
];

/**
 * "Stage n of N" eyebrow for a stage (#3540 OOC sweep: plain, no in-character
 * ordinal). No unknown-stage branch: migration 0110 moved every draft that
 * carried the old stage 4 to stage 5 (#3675), so `findIndex` returning -1 is
 * unreachable after migrate; the clamp only keeps the arithmetic honest and
 * agrees with the page's own Origin fallback ("Stage 1 of N").
 */
export function stageEyebrow(stage: Stage): string {
  const index =
    Math.max(
      CHAPTERS.findIndex((c) => c.stage === stage),
      0
    ) + 1;
  return `Stage ${index} of ${CHAPTERS.length}`;
}

interface ContentsRailProps {
  currentStage: Stage;
  stageCompletion: Record<Stage, boolean>;
  stageErrors: Partial<Record<Stage, string[]>>;
  onStageSelect: (stage: Stage) => void;
  /** The restart door (a button that opens the confirm), rendered under the list. */
  restartSlot?: ReactNode;
}

function stateOf(stage: Stage, current: Stage, done: boolean): 'current' | 'done' | 'later' {
  if (stage === current) return 'current';
  if (done) return 'done';
  return 'later';
}

const STATE_CLASS = { current: 'toc-current', done: 'toc-done', later: 'toc-later' } as const;
const STATE_MARK = { current: '¶', done: '◆', later: '' } as const;
const STATE_SR = {
  current: ', current stage',
  done: ', complete',
  later: ', not yet started',
} as const;

export function ContentsRail({
  currentStage,
  stageCompletion,
  stageErrors,
  onStageSelect,
  restartSlot,
}: ContentsRailProps) {
  return (
    <details className="toc-fold" id="toc-fold" open>
      <summary>
        <span aria-hidden="true">¶</span> {stageEyebrow(currentStage)} ·{' '}
        {STAGE_LABELS[currentStage]} <span className="toc-summary-note">· all stages</span>
      </summary>
      <nav aria-label="Character creation stages">
        <p className="toc-title">Stages</p>
        <ol className="toc-list">
          {CHAPTERS.map(({ stage }, index) => {
            const numeral = String(index + 1);
            const state = stateOf(stage, currentStage, stageCompletion[stage]);
            // Review is never "incomplete" of itself; its reasons are the other chapters'.
            const errors = stage === Stage.REVIEW ? [] : (stageErrors[stage] ?? []);
            return (
              <li key={stage} className={STATE_CLASS[state]}>
                <a
                  href={`#chapter-${stage}`}
                  aria-current={state === 'current' ? 'step' : undefined}
                  onClick={(e) => {
                    e.preventDefault();
                    onStageSelect(stage);
                  }}
                >
                  <span className="toc-mark" aria-hidden="true">
                    {STATE_MARK[state]}
                  </span>
                  <span className="toc-num">{numeral}</span>
                  <span className="toc-label">{STAGE_LABELS[stage]}</span>
                  <span className="vh">{STATE_SR[state]}</span>
                  {state !== 'done' && errors.length > 0 && (
                    <span className="toc-note">
                      <span className="nb">n.b.</span> {errors[0]}
                    </span>
                  )}
                </a>
              </li>
            );
          })}
        </ol>
        {restartSlot && <p className="toc-restart">{restartSlot}</p>}
      </nav>
    </details>
  );
}

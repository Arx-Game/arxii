/**
 * The contents rail (#3540): progress as a table of contents, never a stepper.
 * Eleven chapters with written / current / unwritten state, the validation
 * reason as an "n.b." note, and the restart door beneath. Free navigation is
 * preserved (every chapter is a link). Replaces StageStepper.
 */

import type { ReactNode } from 'react';
import { Stage, STAGE_LABELS } from '../types';

export const CHAPTERS: ReadonlyArray<{ stage: Stage; numeral: string }> = [
  { stage: Stage.ORIGIN, numeral: '1' },
  { stage: Stage.HERITAGE, numeral: '2' },
  { stage: Stage.LINEAGE, numeral: '3' },
  { stage: Stage.DISTINCTIONS, numeral: '4' },
  { stage: Stage.PATH, numeral: '5' },
  { stage: Stage.GIFT, numeral: '6' },
  { stage: Stage.ATTRIBUTES, numeral: '7' },
  { stage: Stage.APPEARANCE, numeral: '8' },
  { stage: Stage.IDENTITY, numeral: '9' },
  { stage: Stage.FINAL_TOUCHES, numeral: '10' },
  { stage: Stage.REVIEW, numeral: '11' },
];

/** "Stage n of 11" eyebrow for a stage (#3540 OOC sweep: plain, no in-character ordinal). */
export function stageEyebrow(stage: Stage): string {
  const index = CHAPTERS.findIndex((c) => c.stage === stage) + 1;
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
  current: ', current chapter',
  done: ', written',
  later: ', not yet written',
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
      <nav aria-label="Chapters of your character">
        <p className="toc-title">Stages</p>
        <ol className="toc-list">
          {CHAPTERS.map(({ stage, numeral }) => {
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

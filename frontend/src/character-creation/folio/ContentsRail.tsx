/**
 * The contents rail (#3540): progress as a table of contents, never a stepper.
 * Eleven chapters with written / current / unwritten state, the validation
 * reason as an "n.b." note, and the restart door beneath. Free navigation is
 * preserved (every chapter is a link). Replaces StageStepper.
 */

import type { ReactNode } from 'react';
import { Stage, STAGE_LABELS } from '../types';

export const CHAPTERS: ReadonlyArray<{ stage: Stage; numeral: string }> = [
  { stage: Stage.ORIGIN, numeral: 'I' },
  { stage: Stage.HERITAGE, numeral: 'II' },
  { stage: Stage.LINEAGE, numeral: 'III' },
  { stage: Stage.DISTINCTIONS, numeral: 'IV' },
  { stage: Stage.PATH, numeral: 'V' },
  { stage: Stage.GIFT, numeral: 'VI' },
  { stage: Stage.ATTRIBUTES, numeral: 'VII' },
  { stage: Stage.APPEARANCE, numeral: 'VIII' },
  { stage: Stage.IDENTITY, numeral: 'IX' },
  { stage: Stage.FINAL_TOUCHES, numeral: 'X' },
  { stage: Stage.REVIEW, numeral: 'XI' },
];

/** "Chapter the First" style eyebrow for a stage; the TOC itself stays Roman. */
export const CHAPTER_ORDINALS: Record<Stage, string> = {
  [Stage.ORIGIN]: 'Chapter the First',
  [Stage.HERITAGE]: 'Chapter the Second',
  [Stage.LINEAGE]: 'Chapter the Third',
  [Stage.DISTINCTIONS]: 'Chapter the Fourth',
  [Stage.PATH]: 'Chapter the Fifth',
  [Stage.GIFT]: 'Chapter the Sixth',
  [Stage.ATTRIBUTES]: 'Chapter the Seventh',
  [Stage.APPEARANCE]: 'Chapter the Eighth',
  [Stage.IDENTITY]: 'Chapter the Ninth',
  [Stage.FINAL_TOUCHES]: 'Chapter the Tenth',
  [Stage.REVIEW]: 'Chapter the Last',
};

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
        <span aria-hidden="true">¶</span> {CHAPTER_ORDINALS[currentStage]} ·{' '}
        {STAGE_LABELS[currentStage]} <span className="toc-summary-note">· the contents</span>
      </summary>
      <nav aria-label="Chapters of your character">
        <p className="toc-title">Contents</p>
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

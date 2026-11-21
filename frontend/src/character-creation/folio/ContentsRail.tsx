/**
 * The contents rail (#3540): progress as a table of contents, never a stepper.
 * The ten stages, the restart door beneath, and free navigation (every stage is a
 * link). Replaces StageStepper.
 *
 * What a row says about its stage (#5199, owner rulings 2026-11-18):
 * - A stage the draft has not been opened on is its name alone. What it will ask is
 *   not printed before the player has seen the stage.
 * - A stage that has been opened and still asks something shows the first thing it
 *   asks after a hyphen (#4022).
 * - A stage with nothing left to ask is marked complete, opened or not.
 * - A stage that asks nothing at all reads "optional" and is never marked complete,
 *   so a new draft does not open with two stages already done. If it has an error all
 *   the same (the points overspent, on Final Touches) and has been opened, the error
 *   shows in place of "optional".
 * The stage the draft stands on always counts as opened.
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
  /** The stages the draft has been opened on, from the server (`visited_stages`). */
  visitedStages: readonly Stage[];
  /** The stages that ask nothing, from the server (`optional_stages`). */
  optionalStages: readonly Stage[];
  onStageSelect: (stage: Stage) => void;
  /** The restart door (a button that opens the confirm), rendered under the list. */
  restartSlot?: ReactNode;
}

type RowState = 'current' | 'done' | 'optional' | 'todo' | 'unopened';

interface RowFacts {
  current: boolean;
  done: boolean;
  optional: boolean;
  opened: boolean;
}

function stateOf({ current, done, optional, opened }: RowFacts): RowState {
  if (current) return 'current';
  if (optional) return 'optional';
  if (done) return 'done';
  return opened ? 'todo' : 'unopened';
}

const STATE_CLASS: Record<RowState, string> = {
  current: 'toc-current',
  done: 'toc-done',
  optional: 'toc-later',
  todo: 'toc-later',
  unopened: 'toc-later',
};
const STATE_MARK: Record<RowState, string> = {
  current: '¶',
  done: '◆',
  optional: '',
  todo: '',
  unopened: '',
};
// "optional" is printed in the row, so it needs no hidden text of its own.
const STATE_SR: Record<RowState, string> = {
  current: ', current stage',
  done: ', complete',
  optional: '',
  todo: ', not finished',
  unopened: ', not yet opened',
};

/** The note after a stage's name: what it still asks, "optional", or nothing. */
function noteFor(facts: RowFacts, errors: string[]): string | null {
  const opened = facts.opened || facts.current;
  if (opened && errors.length > 0 && !facts.done) return `- ${errors[0]}`;
  if (facts.optional) return 'optional';
  return null;
}

export function ContentsRail({
  currentStage,
  stageCompletion,
  stageErrors,
  visitedStages,
  optionalStages,
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
            // Review is never "incomplete" of itself; its reasons are the other chapters'.
            const errors = stage === Stage.REVIEW ? [] : (stageErrors[stage] ?? []);
            const facts: RowFacts = {
              current: stage === currentStage,
              done: stageCompletion[stage],
              optional: optionalStages.includes(stage),
              opened: visitedStages.includes(stage),
            };
            const state = stateOf(facts);
            const note = noteFor(facts, errors);
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
                  {note && <span className="toc-note">{note}</span>}
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

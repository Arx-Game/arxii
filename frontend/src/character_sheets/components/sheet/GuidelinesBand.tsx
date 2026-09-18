/**
 * Goals and guidelines (#3898) — the actor's-sheet answers, gated.
 *
 * These are the likes/dislikes/fears block every OC reference sheet carries, and Dan
 * ruled them private: a stranger should learn what a character would never do by
 * playing with them, or hear a version of it as rumor, not read it off a page. The
 * server already enforces that — `goals` arrives empty when the viewer's access does
 * not meet `goals_visibility` — so this component renders whatever it is handed and
 * never re-implements the tier client-side.
 *
 * Six prompts in a three-column grid keeps the band short even when every one is
 * answered, which is why they moved out of the front page's middle column.
 */

import type { CharacterSheetActorSheet, CharacterSheetGoal } from '@/character_sheets/api';
import { Band } from './primitives';

interface GuidelinesBandProps {
  block: CharacterSheetActorSheet;
  goals: CharacterSheetGoal[];
}

/** One answer. Absent when unanswered — an empty prompt tells a reader nothing. */
function Prompt({ question, answer }: { question: string; answer: string }) {
  if (!answer.trim()) return null;
  return (
    <div className="refsheet-prompt">
      <span className="refsheet-prompt-q">{question}</span>
      <span className="refsheet-prompt-a">{answer}</span>
    </div>
  );
}

/** A horizon's goals, numbered as the player numbered them. */
function GoalsPrompt({ question, goals }: { question: string; goals: CharacterSheetGoal[] }) {
  if (goals.length === 0) return null;
  return (
    <div className="refsheet-prompt">
      <span className="refsheet-prompt-q">{question}</span>
      <ol className="refsheet-prompt-a m-0 list-decimal pl-5">
        {goals.map((goal) => (
          <li key={`${goal.horizon}-${goal.ordinal}`}>{goal.notes || goal.domain}</li>
        ))}
      </ol>
    </div>
  );
}

export function GuidelinesBand({ block, goals }: GuidelinesBandProps) {
  const shortTerm = goals.filter((goal) => goal.horizon === 'short_term');
  const longTerm = goals.filter((goal) => goal.horizon === 'long_term');

  return (
    <Band
      title="Goals and guidelines"
      note="Yours, your friends', or everyone's. Strangers learn these in play, or hear a version as rumor."
    >
      <div className="refsheet-columns-3">
        <Prompt question="They would never" answer={block.never_do} />
        <Prompt question="Protects at all costs" answer={block.protect} />
        <Prompt question="Deathly afraid of" answer={block.fear} />
        <GoalsPrompt question="Wants, soon" goals={shortTerm} />
        <GoalsPrompt question="Wants, someday" goals={longTerm} />
        <Prompt question="Against them" answer={block.enemy_public_line} />
      </div>
      {block.introductions.length > 0 && (
        <div className="mt-4 flex flex-col gap-3 border-t pt-3">
          {block.introductions.map((entry) => (
            <div key={entry.id} className="flex flex-col gap-1">
              <span className="refsheet-prompt-q">{entry.title}</span>
              <p className="refsheet-soft whitespace-pre-wrap text-base italic">{entry.body}</p>
            </div>
          ))}
        </div>
      )}
    </Band>
  );
}

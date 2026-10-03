/**
 * The beats of the life (#4124), on the private sheet.
 *
 * One block per life stage, each beat with the answers the character holds from it
 * and the line the player wrote; an unknown beat prints its name and nothing under
 * it, which is the hook a reader is meant to see. The server sends `beats` to the
 * owner and staff only, so this renders whatever it is handed and never re-implements
 * the gate client-side.
 */

import type { CharacterSheetBeat } from '@/character_sheets/api';
import { Band } from './primitives';

const STAGE_ORDER = ['childhood', 'youth', 'adulthood', 'at_the_glimpse', 'since_the_glimpse'];
const STAGE_LABELS: Record<string, string> = {
  childhood: 'Childhood',
  youth: 'Youth',
  adulthood: 'Before the Glimpse',
  at_the_glimpse: 'At the Glimpse',
  since_the_glimpse: 'Since the Glimpse',
};

export function BeatsBand({ beats }: { beats: CharacterSheetBeat[] }) {
  if (beats.length === 0) return null;
  const stages = STAGE_ORDER.filter((stage) => beats.some((b) => b.life_stage === stage));
  return (
    <Band title="The beats">
      <div className="refsheet-columns-3">
        {stages.map((stage) => (
          <div key={stage} className="refsheet-prompt" data-testid={`beats-${stage}`}>
            <span className="refsheet-prompt-q">{STAGE_LABELS[stage] ?? stage}</span>
            <ul className="refsheet-prompt-a m-0 list-none pl-0">
              {beats
                .filter((b) => b.life_stage === stage)
                .map((beat) => (
                  <li key={beat.beat_id} className="mb-2">
                    <span className="refsheet-entry-name">{beat.name}</span>
                    {!beat.unknown && beat.answers.length > 0 && (
                      <span className="ml-2">{beat.answers.join(', ')}</span>
                    )}
                    {!beat.unknown && beat.line && (
                      <span className="refsheet-note block">{beat.line}</span>
                    )}
                  </li>
                ))}
            </ul>
          </div>
        ))}
      </div>
    </Band>
  );
}

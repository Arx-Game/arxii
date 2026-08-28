/**
 * HallPage — the state-2 logged-in home at `/` (#3412 slice 2), Direction B
 * "Commonplace Book" idiom. Replaces the Gatefold advertisement for any
 * authenticated account (see `GatefoldPage`'s mount branch) — visitors never
 * reach this component.
 *
 * A zero-character account gets the existing `WelcomePanel` remedy content
 * (roster browse / create / pending application) in place of the character
 * grid — its own hasCharacters/pending-application logic is reused as-is,
 * never duplicated here. The Attention and World bands still render for a
 * zero-character account (an empty per-character Attention group, and World
 * band ambiance is account-independent) — only the character grid itself is
 * swapped out.
 *
 * Uses the viewer's own realm/mode tokens (NOT the Gatefold's forced-arx —
 * that's a visitor-advertisement rule, ADR-0227, not a logged-in rule).
 */
import { Plate, PlateHead } from '@/components/folio';
import { WelcomePanel } from '@/components/WelcomePanel';
import { useMyRosterEntriesQuery } from '@/roster/queries';
import { CharactersBand } from './hall/CharactersBand';
import { AttentionBand } from './hall/AttentionBand';
import { WorldBand } from './hall/WorldBand';

export function HallPage() {
  const { data: characters = [] } = useMyRosterEntriesQuery();

  return (
    <div className="container mx-auto space-y-4 px-4 py-6">
      {characters.length === 0 ? (
        <Plate className="p-4">
          <PlateHead as="h2" className="mb-3">
            Your Characters
          </PlateHead>
          <WelcomePanel />
        </Plate>
      ) : (
        <CharactersBand characters={characters} />
      )}

      {/* 52rem, not a default Tailwind breakpoint (brief's explicit threshold) —
          arbitrary variant. Single column below stacks Attention above World
          (attention outranks ambiance). */}
      <div className="min-[52rem]:grid-cols-[1.55fr_1fr] grid grid-cols-1 gap-4">
        <AttentionBand characters={characters} />
        <WorldBand />
      </div>
    </div>
  );
}

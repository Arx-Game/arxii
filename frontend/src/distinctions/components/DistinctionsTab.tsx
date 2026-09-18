/**
 * DistinctionsTab (#1446) — the character sheet's Distinctions section.
 *
 * Ungated: every viewer sees this tab, because the server already filters secret rows for
 * non-privileged viewers (`_build_distinctions`, src/world/character_sheets/serializers.py:501).
 * This component only renders whatever `useCharacterSheetQuery` returns — it does NOT
 * re-implement privacy client-side — and tags rows where `is_secret` is true.
 *
 * Drawn in the Reference Sheet's vocabulary (#3898): one entry per distinction on a
 * hairline rather than a bordered card, and what a row says about itself is a word
 * rather than a number. The old page printed "Rank -1" at a reader, which names a
 * storage detail; the demo says "Disadvantage", and a distinction aimed at a visible
 * feature says so too.
 */

import { useCharacterSheetQuery } from '@/character_sheets/queries';
import { Entries, Entry, Ledger, Tag } from '@/character_sheets/components/sheet/primitives';

interface Props {
  /** CharacterSheet pk (shared with the character ObjectDB pk). */
  characterId: number;
}

export function DistinctionsTab({ characterId }: Props) {
  const { data: payload, isLoading } = useCharacterSheetQuery(characterId);

  if (isLoading) {
    return <Ledger>Reading their distinctions…</Ledger>;
  }

  const distinctions = payload?.distinctions ?? [];

  // One quiet line rather than a card apologising for an empty section. A character
  // genuinely can hold none, and a new one usually does.
  if (distinctions.length === 0) {
    return (
      <p className="refsheet-ledger" data-testid="distinctions-empty-state">
        Nothing set them apart yet.
      </p>
    );
  }

  return (
    <div data-testid="distinctions-list">
      <Entries>
        {distinctions.map((distinction) => (
          <div key={distinction.id} data-testid="distinction-row">
            <Entry
              name={distinction.name}
              tags={
                <>
                  {distinction.rank < 0 && <Tag>Disadvantage</Tag>}
                  {distinction.feature !== '' && <Tag>Distinctive feature</Tag>}
                  {distinction.is_secret && <Tag accent>Secret</Tag>}
                </>
              }
              gloss={distinction.notes || undefined}
            />
          </div>
        ))}
      </Entries>
    </div>
  );
}

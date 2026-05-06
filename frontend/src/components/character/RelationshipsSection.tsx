/**
 * RelationshipsSection
 *
 * Composed panel for character relationships. Two sub-sections:
 * 1. Soul Tethers — SoulTetherStatusPanel displaying active tether bonds.
 * 2. Notes — free-text relationship entries from CharacterData.relationships.
 */

import type { CharacterData } from '@/roster/types';
import { SoulTetherStatusPanel } from '@/magic/components/SoulTetherStatusPanel';
import { useMyTetherBonds } from '@/magic/queries';

interface RelationshipsSectionProps {
  relationships?: CharacterData['relationships'];
  /** The CharacterSheet PK for the viewed character. Passed to SoulTetherStatusPanel. */
  characterSheetId?: number;
}

export function RelationshipsSection({
  relationships,
  characterSheetId,
}: RelationshipsSectionProps) {
  const { data: bonds = [] } = useMyTetherBonds(characterSheetId ?? null);

  const relationshipIds = bonds.map((b) => b.relationship_id);

  const bondedCharacterNames: Record<number, string> = {};
  for (const bond of bonds) {
    bondedCharacterNames[bond.relationship_id] = bond.bonded_character_name;
  }

  return (
    <section>
      <h3 className="text-xl font-semibold">Relationships</h3>

      <div className="mt-4 space-y-6">
        {/* Sub-section: Soul Tether bonds */}
        <SoulTetherStatusPanel
          relationshipIds={relationshipIds}
          callerSheetId={characterSheetId}
          bondedCharacterNames={bondedCharacterNames}
        />

        {/* Sub-section: Notes (free-text) */}
        <div>
          <h4 className="text-lg font-medium">Notes</h4>
          <ul className="list-disc pl-5">
            {relationships?.length ? (
              relationships.map((rel) => <li key={rel}>{rel}</li>)
            ) : (
              <li>TBD</li>
            )}
          </ul>
        </div>
      </div>
    </section>
  );
}

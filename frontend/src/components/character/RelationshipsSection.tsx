/**
 * RelationshipsSection
 *
 * Composed panel for character relationships. Two sub-sections:
 * 1. Soul Tethers — SoulTetherStatusPanel displaying active tether bonds.
 * 2. Notes — free-text relationship entries from CharacterData.relationships.
 *
 * Soul Tether bond discovery: there is currently no endpoint that lists a
 * character's tether bonds by ID. Phase 4 passes `relationshipIds={[]}`,
 * which renders the "No active soul tethers." empty state. A follow-up task
 * should add a `GET /api/magic/soul-tether/?character_sheet_id=<id>` list
 * endpoint and wire it here.
 * TODO(soul-tether-phase5): enumerate tether bond IDs from backend and pass to panel.
 */

import type { CharacterData } from '@/roster/types';
import { SoulTetherStatusPanel } from '@/magic/components/SoulTetherStatusPanel';

interface RelationshipsSectionProps {
  relationships?: CharacterData['relationships'];
  /** The CharacterSheet PK for the viewed character. Passed to SoulTetherStatusPanel. */
  characterSheetId?: number;
  /**
   * Optional map of relationship ID → bonded character name.
   * If absent, SoulTetherStatusPanel falls back to "#<sheet_id>".
   */
  bondedCharacterNames?: Record<number, string>;
}

export function RelationshipsSection({
  relationships,
  characterSheetId,
  bondedCharacterNames,
}: RelationshipsSectionProps) {
  // No tether-bond enumeration endpoint exists yet. Pass empty list so the panel
  // renders its graceful empty state. See module-level TODO above.
  const relationshipIds: number[] = [];

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

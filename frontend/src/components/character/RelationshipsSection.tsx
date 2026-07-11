/**
 * RelationshipsSection
 *
 * Composed panel for character relationships. Three sub-sections:
 * 1. Soul Tethers — SoulTetherStatusPanel displaying active tether bonds.
 * 2. Writeups — commendable relationship writeups about the OWN character (#2031).
 * 3. Notes — free-text relationship entries from CharacterData.relationships.
 */

import { useState } from 'react';

import type { CharacterData } from '@/roster/types';
import { SoulTetherStatusPanel } from '@/magic/components/SoulTetherStatusPanel';
import { useMyTetherBonds } from '@/magic/queries';
import { useGiveWriteupKudos, useMyWriteups } from '@/relationships/queries';

interface RelationshipsSectionProps {
  relationships?: CharacterData['relationships'];
  /** The CharacterSheet PK for the viewed character. Passed to SoulTetherStatusPanel. */
  characterSheetId?: number;
  /**
   * True only when viewing the CALLER's own character sheet.
   *
   * The writeups list endpoint (GET /api/relationships/relationship-updates/)
   * is scoped to the requesting user's *account* (tenure-based — every
   * character the account currently owns), not to any single viewed
   * character. `characterSheetId` is passed through as `?subject_character=`
   * to narrow the account-wide set down to just the viewed character's
   * writeups, so a multi-character account's sibling writeups never leak
   * onto the wrong sheet's tab (fix wave, Finding 2). `isMyCharacter` itself
   * mirrors `useMyRosterEntriesQuery`'s tenure-based ownership check
   * (CharacterSheetPage.tsx), which now has the SAME tenure semantics as the
   * backend's subject scoping — so gating on it here is correct for any
   * owned character, not just the currently-puppeted one. It still gates
   * both the query and the subsection's render, so a foreign-sheet viewer
   * neither fetches nor sees this subsection.
   */
  isMyCharacter?: boolean;
}

export function RelationshipsSection({
  relationships,
  characterSheetId,
  isMyCharacter = false,
}: RelationshipsSectionProps) {
  const { data: bonds = [] } = useMyTetherBonds(characterSheetId ?? null);
  const { data: writeups = [] } = useMyWriteups(characterSheetId, isMyCharacter);
  const giveKudos = useGiveWriteupKudos();
  const [kudosError, setKudosError] = useState<string | null>(null);

  const relationshipIds = bonds.map((b) => b.relationship_id);

  const bondedCharacterNames: Record<number, string> = {};
  for (const bond of bonds) {
    bondedCharacterNames[bond.relationship_id] = bond.bonded_character_name;
  }

  const handleCommend = (writeupId: number) => {
    setKudosError(null);
    giveKudos.mutate(
      { writeup_type: 'update', writeup_id: writeupId },
      {
        onError: (err) => {
          setKudosError(err instanceof Error ? err.message : 'Failed to commend this writeup');
        },
      }
    );
  };

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

        {/* Sub-section: Writeups (only shown when writeups exist) */}
        {writeups.length > 0 && (
          <div>
            <h4 className="text-lg font-medium">Writeups</h4>
            {kudosError && (
              <p role="alert" className="text-sm text-destructive">
                {kudosError}
              </p>
            )}
            <ul className="space-y-4">
              {writeups.map((writeup) => (
                <li key={writeup.id} className="border-b pb-3">
                  <p className="font-medium">{writeup.title}</p>
                  <p className="text-sm text-muted-foreground">By {writeup.author_name}</p>
                  <p className="mt-1">{writeup.writeup}</p>
                  <div className="mt-2 flex items-center gap-3">
                    <span className="text-sm text-muted-foreground">
                      {writeup.kudos_count} kudos
                    </span>
                    {!writeup.viewer_has_kudosed && (
                      <button
                        type="button"
                        onClick={() => handleCommend(writeup.id)}
                        disabled={giveKudos.isPending}
                      >
                        Commend
                      </button>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Sub-section: Notes (free-text) */}
        <div>
          <h4 className="text-lg font-medium">Notes</h4>
          <ul className="list-disc pl-5">
            {relationships?.length ? (
              relationships.map((rel) => <li key={rel}>{rel}</li>)
            ) : (
              <li className="text-muted-foreground">No relationship notes yet.</li>
            )}
          </ul>
        </div>
      </div>
    </section>
  );
}

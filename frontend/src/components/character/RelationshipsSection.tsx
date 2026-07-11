/**
 * RelationshipsSection
 *
 * Composed panel for character relationships. Three sub-sections:
 * 1. Soul Tethers — SoulTetherStatusPanel displaying active tether bonds.
 * 2. Writeups — commendable relationship writeups about the OWN character (#2031),
 *    plus a "Report" button (#2159) filing a staff-triage bad-faith-RP complaint.
 * 3. Ties — RelationshipPanel (#2159): own sheet gets the full outbound relationship
 *    list (tracks/tiers/history); a foreign sheet gets the visibility-scoped timeline.
 *    Replaces the old free-text `CharacterData.relationships` Notes subsection, which
 *    no longer renders.
 */

import { useState } from 'react';

import { SoulTetherStatusPanel } from '@/magic/components/SoulTetherStatusPanel';
import { useMyTetherBonds } from '@/magic/queries';
import { useGiveWriteupKudos, useMyWriteups } from '@/relationships/queries';
import { RelationshipPanel } from '@/relationships/components/RelationshipPanel';
import { WriteupComplaintDialog } from '@/relationships/components/WriteupComplaintDialog';

interface RelationshipsSectionProps {
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
  characterSheetId,
  isMyCharacter = false,
}: RelationshipsSectionProps) {
  const { data: bonds = [] } = useMyTetherBonds(characterSheetId ?? null);
  const { data: writeups = [] } = useMyWriteups(characterSheetId, isMyCharacter);
  const giveKudos = useGiveWriteupKudos();
  const [kudosError, setKudosError] = useState<string | null>(null);
  const [complaintTarget, setComplaintTarget] = useState<{
    writeupId: number;
    title: string;
  } | null>(null);

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
                    <button
                      type="button"
                      onClick={() =>
                        setComplaintTarget({ writeupId: writeup.id, title: writeup.title })
                      }
                    >
                      Report
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Sub-section: Ties (#2159) — real relationship state, replacing free-text Notes */}
        <div>
          <h4 className="text-lg font-medium">Ties</h4>
          <RelationshipPanel characterSheetId={characterSheetId} isMyCharacter={isMyCharacter} />
        </div>
      </div>

      {complaintTarget && (
        <WriteupComplaintDialog
          open
          onOpenChange={(open) => {
            if (!open) setComplaintTarget(null);
          }}
          writeupType="update"
          writeupId={complaintTarget.writeupId}
          writeupTitle={complaintTarget.title}
        />
      )}
    </section>
  );
}

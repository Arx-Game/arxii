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
 *
 * Drawn in the Reference Sheet's vocabulary (#3898): entries on hairlines, not cards,
 * and NO heading of its own — the sheet draws "Relationships" above this, and a second
 * one here read as a duplicate.
 */

import { useState } from 'react';

import { SoulTetherStatusPanel } from '@/magic/components/SoulTetherStatusPanel';
import { useMyTetherBonds } from '@/magic/queries';
import { useGiveWriteupKudos, useMyWriteups } from '@/relationships/queries';
import { RelationshipPanel } from '@/relationships/components/RelationshipPanel';
import { WriteupComplaintDialog } from '@/relationships/components/WriteupComplaintDialog';
import {
  Entries,
  Entry,
  QuietDoor,
  Stack,
  Subheading,
} from '@/character_sheets/components/sheet/primitives';

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
    <Stack wide>
      <SoulTetherStatusPanel
        relationshipIds={relationshipIds}
        callerSheetId={characterSheetId}
        bondedCharacterNames={bondedCharacterNames}
      />

      {writeups.length > 0 && (
        <Stack>
          <Subheading>Writeups</Subheading>
          {kudosError && (
            <p role="alert" className="refsheet-note" style={{ color: 'hsl(var(--destructive))' }}>
              {kudosError}
            </p>
          )}
          <Entries>
            {writeups.map((writeup) => (
              <Entry
                key={writeup.id}
                name={writeup.title}
                aside={<span className="refsheet-note">{writeup.kudos_count} kudos</span>}
                gloss={`By ${writeup.author_name}`}
              >
                <p className="refsheet-entry-gloss">{writeup.writeup}</p>
                <div className="refsheet-doors">
                  {!writeup.viewer_has_kudosed && (
                    <QuietDoor
                      onClick={() => handleCommend(writeup.id)}
                      disabled={giveKudos.isPending}
                    >
                      Commend
                    </QuietDoor>
                  )}
                  <QuietDoor
                    onClick={() =>
                      setComplaintTarget({ writeupId: writeup.id, title: writeup.title })
                    }
                  >
                    Report
                  </QuietDoor>
                </div>
              </Entry>
            ))}
          </Entries>
        </Stack>
      )}

      <Stack>
        <Subheading>Ties</Subheading>
        <RelationshipPanel characterSheetId={characterSheetId} isMyCharacter={isMyCharacter} />
      </Stack>

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
    </Stack>
  );
}

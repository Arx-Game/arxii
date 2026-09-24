/**
 * The Relationships block on the sheet's Ties section (#3957).
 *
 * Two things, in this order: any soul tether the character holds, then the cast.
 *
 * What used to be here is gone with the redesign. The Writeups block asked the player
 * to write a weekly development update to earn points, and points-per-track are what
 * ties replaced: depth comes from scenes the two were in and one AP number per tie, so
 * there is no writeup to commend and no complaint surface hanging off one. The old
 * panel's own-vs-foreign branch is gone too — the server ships the cast already shaped
 * for whoever is reading, so there is nothing left for this component to decide.
 */

import { SoulTetherStatusPanel } from '@/magic/components/SoulTetherStatusPanel';
import { useMyTetherBonds } from '@/magic/queries';
import { TieCast } from '@/relationships/components/TieCast';
import { Stack } from '@/character_sheets/components/sheet/primitives';
import type { CharacterSheetTie } from '@/character_sheets/api';

export interface RelationshipsSectionProps {
  /** The CharacterSheet PK for the viewed character. Passed to SoulTetherStatusPanel. */
  characterSheetId?: number;
  /** The viewed character's RosterEntry id — every tie page hangs off it. */
  entryId: number;
  /** True only when viewing the CALLER's own character. Gates the AP ledger and the way in. */
  isMyCharacter?: boolean;
  /** The cast, straight off the sheet payload — already audience-shaped server-side. */
  ties: CharacterSheetTie[];
  /** AP set across every tie this week; null for anyone but the owner and staff. */
  tiesApThisWeek: number | null;
}

export function RelationshipsSection({
  characterSheetId,
  entryId,
  isMyCharacter = false,
  ties,
  tiesApThisWeek,
}: RelationshipsSectionProps) {
  const { data: bonds = [] } = useMyTetherBonds(characterSheetId ?? null);

  const relationshipIds = bonds.map((bond) => bond.relationship_id);
  const bondedCharacterNames: Record<number, string> = {};
  for (const bond of bonds) {
    bondedCharacterNames[bond.relationship_id] = bond.bonded_character_name;
  }

  return (
    <Stack wide>
      <SoulTetherStatusPanel
        relationshipIds={relationshipIds}
        callerSheetId={characterSheetId}
        bondedCharacterNames={bondedCharacterNames}
      />
      <TieCast
        ties={ties}
        entryId={entryId}
        isMyCharacter={isMyCharacter}
        apThisWeek={tiesApThisWeek}
      />
    </Stack>
  );
}

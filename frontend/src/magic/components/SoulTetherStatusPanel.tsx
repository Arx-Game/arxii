/**
 * SoulTetherStatusPanel
 *
 * The caller's Soul Tether bonds. For each bond it shows:
 * - Bonded character name (from bondedCharacterNames prop, or "#<id>" fallback)
 * - Role label (Sinner / Sineater), derived from callerSheetId vs the detail payload
 * - HollowBar (current/max)
 * - lifetime_helped (shown only when caller is the Sineater)
 *
 * Contract decision: accepts `relationshipIds` (array of CharacterRelationship PKs)
 * and optionally `callerSheetId` (so we can determine which side of each bond the
 * caller occupies). The parent (Phase 4 RelationshipsSection) is responsible for
 * supplying which relationship IDs are Soul Tether bonds. This keeps the panel
 * decoupled from bond discovery.
 *
 * Name display decision: parent optionally passes `bondedCharacterNames` as a
 * Record<relationshipId, name>. If a name is missing, the panel falls back to
 * displaying the bonded character's sheet ID prefixed with "#". This avoids
 * needing a separate character-sheet lookup hook.
 *
 * Drawn in the Reference Sheet's vocabulary (#3898): a subheading over entries on
 * hairlines, and NOTHING at all when there are no tethers. The card this used to be,
 * whose whole body was the words "No active soul tethers.", is the empty-state card
 * the sheet's rulings forbid — it took a reader's attention to tell them nothing.
 */

import { HollowBar } from '@/magic/components/HollowBar';
import { Entries, Entry, Stack, Subheading } from '@/character_sheets/components/sheet/primitives';
import { useSoulTetherDetail } from '@/magic/queries';
import type { SoulTetherDetail } from '@/magic/types';

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface SoulTetherStatusPanelProps {
  /** PKs of the CharacterRelationship rows that are Soul Tether bonds. */
  relationshipIds: number[];
  /**
   * The caller's CharacterSheet PK. Used to determine which side of each bond
   * the caller occupies (Sinner vs Sineater) and to derive the bonded party's
   * sheet ID for fallback name display.
   *
   * When omitted, role detection defaults to "Sinner" and the bonded character
   * cannot be determined — names will always fall back to the name map or IDs.
   */
  callerSheetId?: number;
  /**
   * Optional map of relationship ID → bonded character name. If absent for a
   * given bond, the panel displays "#<sheet_id>" as a fallback. The parent
   * (RelationshipsSection) populates this from the relationship list it already
   * holds.
   */
  bondedCharacterNames?: Record<number, string>;
}

// ---------------------------------------------------------------------------
// Helper: derive caller role and bonded sheet ID from detail + callerSheetId
// ---------------------------------------------------------------------------

function deriveBondInfo(
  detail: SoulTetherDetail,
  callerSheetId: number | undefined
): { callerIsSineater: boolean; bondedSheetId: number | null } {
  const { sinner_sheet_id, sineater_sheet_id } = detail;

  if (callerSheetId === undefined) {
    // Cannot determine — assume Sinner
    return { callerIsSineater: false, bondedSheetId: sineater_sheet_id };
  }

  const callerIsSineater = callerSheetId === sineater_sheet_id;
  const bondedSheetId = callerIsSineater ? sinner_sheet_id : sineater_sheet_id;
  return { callerIsSineater, bondedSheetId };
}

// ---------------------------------------------------------------------------
// Sub-component: single bond row
// ---------------------------------------------------------------------------

interface BondRowProps {
  relationshipId: number;
  callerSheetId: number | undefined;
  bondedCharacterNames: Record<number, string> | undefined;
}

function BondRow({ relationshipId, callerSheetId, bondedCharacterNames }: BondRowProps) {
  const { data, isLoading, isError } = useSoulTetherDetail(relationshipId);

  if (isLoading) {
    return <p className="refsheet-ledger">Loading tether…</p>;
  }

  if (isError || !data) {
    return (
      <p className="refsheet-ledger" style={{ color: 'hsl(var(--destructive))' }}>
        That tether could not be read.
      </p>
    );
  }

  const { callerIsSineater, bondedSheetId } = deriveBondInfo(data, callerSheetId);

  // Resolve bonded character name: prop map → sheet ID fallback
  const bondedName =
    bondedCharacterNames?.[relationshipId] ??
    (bondedSheetId != null ? `#${bondedSheetId}` : 'Unknown');

  const roleLabel = callerIsSineater ? 'Sineater' : 'Sinner';

  return (
    <Entry
      name={bondedName}
      aside={<span className="refsheet-note">{roleLabel}</span>}
      gloss={
        callerIsSineater ? `${data.sineater_lifetime_helped} units helped, all told.` : undefined
      }
    >
      <HollowBar current={data.hollow_current} max={data.hollow_max} />
    </Entry>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function SoulTetherStatusPanel({
  relationshipIds,
  callerSheetId,
  bondedCharacterNames,
}: SoulTetherStatusPanelProps) {
  // Render-or-vanish: a character with no tether has no tether block, not a block
  // announcing the absence.
  if (relationshipIds.length === 0) return null;
  return (
    <Stack>
      <Subheading>Soul tethers</Subheading>
      <Entries>
        {relationshipIds.map((id) => (
          <BondRow
            key={id}
            relationshipId={id}
            callerSheetId={callerSheetId}
            bondedCharacterNames={bondedCharacterNames}
          />
        ))}
      </Entries>
    </Stack>
  );
}

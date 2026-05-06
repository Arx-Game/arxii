/**
 * SoulTetherStatusPanel
 *
 * Card showing the caller's Soul Tether bonds. For each bond it displays:
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
 * Pattern: modeled after VotesPanel (header card + item rows).
 */

import { Link2 } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { HollowBar } from '@/magic/components/HollowBar';
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
    return <li className="py-2 text-sm text-muted-foreground">Loading tether…</li>;
  }

  if (isError || !data) {
    return (
      <li className="py-2 text-sm text-destructive">Failed to load tether {relationshipId}.</li>
    );
  }

  const { callerIsSineater, bondedSheetId } = deriveBondInfo(data, callerSheetId);

  // Resolve bonded character name: prop map → sheet ID fallback
  const bondedName =
    bondedCharacterNames?.[relationshipId] ??
    (bondedSheetId != null ? `#${bondedSheetId}` : 'Unknown');

  const roleLabel = callerIsSineater ? 'Sineater' : 'Sinner';

  return (
    <li className="space-y-2 rounded-md border p-3">
      <div className="flex items-center justify-between text-sm">
        <span className="font-medium">{bondedName}</span>
        <span className="rounded bg-muted px-1.5 py-0.5 text-xs text-muted-foreground">
          {roleLabel}
        </span>
      </div>
      <HollowBar current={data.hollow_current} max={data.hollow_max} />
      {callerIsSineater && (
        <p className="text-xs text-muted-foreground">
          {data.sineater_lifetime_helped} units helped (lifetime)
        </p>
      )}
    </li>
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
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <Link2 className="h-4 w-4" />
          Soul Tethers
        </CardTitle>
      </CardHeader>
      <CardContent>
        {relationshipIds.length > 0 ? (
          <ul className="space-y-3">
            {relationshipIds.map((id) => (
              <BondRow
                key={id}
                relationshipId={id}
                callerSheetId={callerSheetId}
                bondedCharacterNames={bondedCharacterNames}
              />
            ))}
          </ul>
        ) : (
          <p className="text-center text-sm text-muted-foreground">No active soul tethers.</p>
        )}
      </CardContent>
    </Card>
  );
}

/**
 * RitesPanel — covenant "Group Abilities" (rites) display + trigger surface.
 *
 * Lists a covenant's authored rites (from useCovenantPowers), each with its
 * activation gates (covenant level + members present) rendered as requirement
 * chips. A rite's Perform button is enabled only when both gates are met, the
 * viewer is an active member, and an active character sheet is known. Clicking
 * Perform opens the shared RitualSessionDraftDialog for the rite's resolved
 * ritual, navigating to the new session on success (mirrors the induction flow
 * in CovenantDetailPage).
 *
 * Read-only counterpart panels (role powers, battle state) live alongside this
 * one; this component owns only the rites surface.
 */

import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useCovenantPowers } from '@/covenants/queries';
import { useRituals } from '@/rituals/queries';
import { RitualSessionDraftDialog } from '@/rituals/components/RitualSessionDraftDialog';
import type { CovenantRiteRow } from '@/covenants/api';
import type { RitualWithSchema } from '@/rituals/types';

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface RitesPanelProps {
  covenantId: number;
  /** Whether the viewing character is an active member of this covenant. */
  isActiveMember: boolean;
  /** The viewing character's sheet id, or null when no character is puppeted. */
  characterSheetId: number | null;
}

// ---------------------------------------------------------------------------
// Single rite card
// ---------------------------------------------------------------------------

interface RiteCardProps {
  rite: CovenantRiteRow;
  ritual: RitualWithSchema | null;
  isActiveMember: boolean;
  characterSheetId: number | null;
  onPerform: () => void;
}

function RiteCard({ rite, ritual, isActiveMember, characterSheetId, onPerform }: RiteCardProps) {
  const label = ritual?.name ?? `Rite #${rite.id}`;

  // Gate evaluation. Order the blocking reasons most-fundamental first.
  let blockedReason: string | null = null;
  if (ritual === null) {
    blockedReason = 'Ritual unavailable';
  } else if (!rite.level_met) {
    blockedReason = `Requires covenant level ${rite.min_covenant_level}`;
  } else if (!rite.members_present_met) {
    blockedReason = `Requires ${rite.min_members_present} members present`;
  } else if (!isActiveMember) {
    blockedReason = 'Only active members can perform rites';
  } else if (characterSheetId === null) {
    blockedReason = 'No active character';
  }

  const canPerform = blockedReason === null;

  return (
    <Card data-testid="rite-card">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between gap-3">
          <CardTitle className="text-base">{label}</CardTitle>
          <Badge variant="outline" className="text-xs">
            {rite.covenant_type_display}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {/* Requirement chips */}
        <div className="flex flex-wrap gap-1">
          <Badge variant={rite.level_met ? 'outline' : 'secondary'} className="text-xs">
            Level {rite.min_covenant_level}
          </Badge>
          <Badge variant={rite.members_present_met ? 'outline' : 'secondary'} className="text-xs">
            {rite.min_members_present} present
          </Badge>
          {rite.duration_rounds !== null && (
            <Badge variant="outline" className="text-xs">
              {rite.duration_rounds} rounds
            </Badge>
          )}
          {rite.max_severity !== null && (
            <Badge variant="outline" className="text-xs">
              Severity {rite.base_severity}–{rite.max_severity}
            </Badge>
          )}
        </div>

        {/* Action + gate reason */}
        <div className="flex items-center justify-between gap-3">
          <Button
            size="sm"
            onClick={onPerform}
            disabled={!canPerform}
            title={blockedReason ?? undefined}
            data-testid="rite-perform-button"
          >
            Perform
          </Button>
          {blockedReason && (
            <p className="text-xs text-muted-foreground" data-testid="rite-blocked-reason">
              {blockedReason}
            </p>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Panel
// ---------------------------------------------------------------------------

export function RitesPanel({ covenantId, isActiveMember, characterSheetId }: RitesPanelProps) {
  const navigate = useNavigate();
  const { data: powers, isLoading: powersLoading } = useCovenantPowers(covenantId);
  const { data: ritualsData, isLoading: ritualsLoading } = useRituals();

  // Which rite's draft dialog is open (rite id), or null.
  const [openRiteId, setOpenRiteId] = useState<number | null>(null);

  if (powersLoading) {
    return null;
  }

  const rites = powers?.rites ?? [];
  const allRituals = !ritualsLoading ? ((ritualsData?.results ?? []) as RitualWithSchema[]) : [];

  function resolveRitual(rite: CovenantRiteRow): RitualWithSchema | null {
    return allRituals.find((r) => r.id === rite.ritual) ?? null;
  }

  const openRite = openRiteId !== null ? rites.find((r) => r.id === openRiteId) : undefined;
  const openRitual = openRite ? resolveRitual(openRite) : null;

  return (
    <section>
      <h2 className="mb-3 text-lg font-semibold">Group Abilities</h2>

      {rites.length === 0 ? (
        <p className="py-4 text-center text-sm text-muted-foreground">
          No group abilities available.
        </p>
      ) : (
        <div className="space-y-3" data-testid="rites-list">
          {rites.map((rite) => (
            <RiteCard
              key={rite.id}
              rite={rite}
              ritual={resolveRitual(rite)}
              isActiveMember={isActiveMember}
              characterSheetId={characterSheetId}
              onPerform={() => setOpenRiteId(rite.id)}
            />
          ))}
        </div>
      )}

      {/* Draft dialog for the open rite. Mirrors the induction flow: pass the
          resolved ritual + character sheet, navigate to the session on success. */}
      {openRite && openRitual && characterSheetId !== null && (
        <RitualSessionDraftDialog
          ritual={openRitual}
          characterSheetId={characterSheetId}
          open={true}
          onOpenChange={(next) => {
            if (!next) setOpenRiteId(null);
          }}
          onSuccess={(session) => {
            setOpenRiteId(null);
            navigate(`/rituals/sessions/${session.id}`);
          }}
        />
      )}
    </section>
  );
}

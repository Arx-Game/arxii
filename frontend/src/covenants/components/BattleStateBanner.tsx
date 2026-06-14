/**
 * BattleStateBanner — battle-covenant dormant/risen state + rise/stand-down.
 *
 * Renders only for BATTLE covenants. A dormant battle covenant shows a muted
 * "dormant" banner with a "Raise" control that fires the ritual-driven rise
 * flow ("Call the Banners") via the shared RitualSessionDraftDialog — mirroring
 * the induction flow in CovenantDetailPage / RitesPanel. A risen covenant shows
 * a positive banner with a "Stand Down" control that calls the stand-down
 * mutation directly.
 *
 * Single responsibility: this component owns only the battle-state surface. The
 * rite/role-power panels live alongside it.
 */

import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { useStandDownCovenant } from '@/covenants/queries';
import { useRituals } from '@/rituals/queries';
import { RitualSessionDraftDialog } from '@/rituals/components/RitualSessionDraftDialog';
import type { CovenantWithBattleState } from '@/covenants/api';
import type { RitualWithSchema } from '@/rituals/types';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** Stored CovenantType value for battle covenants (CovenantType.BATTLE). */
const BATTLE_COVENANT_TYPE = 'battle';

/** Name of the ritual that dispatches rise_battle_covenant_via_session. */
const RISE_RITUAL_NAME = 'Call the Banners';

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface BattleStateBannerProps {
  covenant: CovenantWithBattleState;
  /** The viewing character's sheet id, or null when no character is puppeted. */
  characterSheetId: number | null;
  /** Whether the viewing character is an active member of this covenant. */
  isActiveMember: boolean;
}

// ---------------------------------------------------------------------------
// Helper: resolve the rise ritual by name
// ---------------------------------------------------------------------------

function findRiseRitual(rituals: RitualWithSchema[]): RitualWithSchema | null {
  return rituals.find((r) => r.name === RISE_RITUAL_NAME) ?? null;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function BattleStateBanner({
  covenant,
  characterSheetId,
  isActiveMember,
}: BattleStateBannerProps) {
  const navigate = useNavigate();
  const standDown = useStandDownCovenant(covenant.id);
  const { data: ritualsData, isLoading: ritualsLoading } = useRituals();
  const [riseDialogOpen, setRiseDialogOpen] = useState(false);

  // Non-battle covenants render nothing.
  if (covenant.covenant_type !== BATTLE_COVENANT_TYPE) {
    return null;
  }

  const allRituals = !ritualsLoading ? ((ritualsData?.results ?? []) as RitualWithSchema[]) : [];
  const riseRitual = findRiseRitual(allRituals);

  const bindingChip = covenant.battle_binding_display ? (
    <Badge variant="outline" className="text-xs uppercase tracking-wide">
      {covenant.battle_binding_display}
    </Badge>
  ) : null;

  // ----- Dormant -----------------------------------------------------------
  if (covenant.is_dormant) {
    let raiseBlockedReason: string | null = null;
    if (!isActiveMember) {
      raiseBlockedReason = 'Only active members can raise the covenant';
    } else if (characterSheetId === null) {
      raiseBlockedReason = 'No active character';
    } else if (riseRitual === null) {
      raiseBlockedReason = 'Rise ritual unavailable';
    }
    const canRaise = raiseBlockedReason === null;

    return (
      <section
        data-testid="battle-state-banner"
        className="rounded-md border border-destructive/40 bg-destructive/10 p-4"
      >
        <div className="flex items-center justify-between gap-3">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-semibold text-destructive">Dormant</h3>
              {bindingChip}
            </div>
            <p className="text-sm text-muted-foreground">This battle covenant is dormant.</p>
          </div>
          <Button
            size="sm"
            onClick={() => setRiseDialogOpen(true)}
            disabled={!canRaise}
            title={raiseBlockedReason ?? undefined}
            data-testid="battle-raise-button"
          >
            Raise
          </Button>
        </div>

        {/* Rise dialog — mirrors induction: pass the resolved ritual + sheet,
            navigate to the new session on success. */}
        {riseRitual && characterSheetId !== null && (
          <RitualSessionDraftDialog
            ritual={riseRitual}
            characterSheetId={characterSheetId}
            open={riseDialogOpen}
            onOpenChange={setRiseDialogOpen}
            onSuccess={(session) => {
              setRiseDialogOpen(false);
              navigate(`/rituals/sessions/${session.id}`);
            }}
          />
        )}
      </section>
    );
  }

  // ----- Risen -------------------------------------------------------------
  return (
    <section
      data-testid="battle-state-banner"
      className="rounded-md border border-emerald-500/40 bg-emerald-500/10 p-4"
    >
      <div className="flex items-center justify-between gap-3">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold text-emerald-600 dark:text-emerald-400">Risen</h3>
            {bindingChip}
          </div>
          <p className="text-sm text-muted-foreground">This battle covenant has risen to war.</p>
        </div>
        <Button
          size="sm"
          variant="outline"
          onClick={() => standDown.mutate()}
          disabled={!isActiveMember || standDown.isPending}
          title={!isActiveMember ? 'Only active members can stand the covenant down' : undefined}
          data-testid="battle-stand-down-button"
        >
          {standDown.isPending ? 'Standing down…' : 'Stand Down'}
        </Button>
      </div>
    </section>
  );
}

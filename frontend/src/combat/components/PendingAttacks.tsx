/**
 * PendingAttacks (#3572) - the threat strip: every telegraphed wind-up still winding
 * up on this encounter, who it is aimed at, when it lands, and how badly it has been
 * wrecked. Rendered inside YourTurn with prefill callbacks (Guard the target / Strike
 * the foe) and in CombatTurnPanel for observers without them. Renders nothing when
 * there are no pending wind-ups.
 */

import { cn } from '@/lib/utils';
import type { PendingAttack } from '../types';

// Mirrors the backend's WINDUP_FIZZLE_DOWNGRADES (the wreck-cancel threshold) - keep
// these two in lockstep if that value ever changes.
const PIP_COUNT = 3;

export interface PendingAttacksProps {
  attacks: PendingAttack[];
  /** The viewer's own CombatParticipant id, or null for observers. */
  viewerParticipantId: number | null;
  /** Prefill the Guard control with this ally. Absent = no button (observer). */
  onGuard?: (targetParticipantId: number) => void;
  /** Prefill the focused declaration's target with this opponent. Absent = no button. */
  onStrike?: (opponentId: number) => void;
}

function landingLabel(attack: PendingAttack): string {
  if (attack.rounds_until_landing <= 0) return 'lands this round';
  return `lands in ${attack.rounds_until_landing}`;
}

function DowngradePips({ downgrades }: { downgrades: number }) {
  return (
    <span
      className="inline-flex gap-0.5"
      aria-label={`${Math.min(downgrades, PIP_COUNT)} of ${PIP_COUNT} staggers`}
    >
      {Array.from({ length: PIP_COUNT }, (_, i) => {
        const filled = i < downgrades;
        return (
          <span
            key={i}
            data-testid={filled ? 'downgrade-pip-filled' : 'downgrade-pip-empty'}
            className={cn(
              'h-2 w-2 rounded-full border border-amber-500',
              filled ? 'bg-amber-400' : 'bg-transparent'
            )}
          />
        );
      })}
    </span>
  );
}

export function PendingAttacks({
  attacks,
  viewerParticipantId,
  onGuard,
  onStrike,
}: PendingAttacksProps) {
  if (attacks.length === 0) return null;
  return (
    <div className="space-y-1" data-testid="pending-attacks">
      <p className="text-xs font-semibold uppercase tracking-wide text-amber-300">Wind-ups</p>
      {attacks.map((attack) => {
        const targetId = attack.target_participant_id;
        const canGuard = onGuard != null && targetId != null && targetId !== viewerParticipantId;
        return (
          <div
            key={attack.id}
            data-testid={`pending-attack-${attack.id}`}
            className={cn(
              'flex flex-wrap items-center gap-2 rounded-md border px-2 py-1.5 text-xs',
              attack.cancelled
                ? 'border-border bg-muted text-muted-foreground line-through'
                : 'border-amber-500/50 bg-amber-950/30 text-amber-100'
            )}
          >
            <span className="font-medium">
              {attack.opponent_name} {'→'} {attack.target_name ?? 'no one in particular'}
            </span>
            <span className="text-muted-foreground">{landingLabel(attack)}</span>
            <DowngradePips downgrades={attack.downgrades} />
            {attack.called_out && (
              <span className="rounded border border-amber-400 px-1 text-[10px] uppercase">
                called out
              </span>
            )}
            {attack.cancelled && (
              <span className="rounded border border-muted-foreground px-1 text-[10px] uppercase">
                broken
              </span>
            )}
            {canGuard && (
              <button
                type="button"
                data-testid={`pending-attack-guard-${attack.id}`}
                onClick={() => onGuard(targetId)}
                className="ml-auto rounded border border-primary/40 bg-primary/10 px-2 py-0.5 text-primary hover:bg-primary/20"
              >
                Guard {attack.target_name}
              </button>
            )}
            {onStrike != null && !attack.cancelled && (
              <button
                type="button"
                data-testid={`pending-attack-strike-${attack.id}`}
                onClick={() => onStrike(attack.opponent_id)}
                className={cn(
                  'rounded border border-red-500/40 bg-red-500/10 px-2 py-0.5 text-red-300 hover:bg-red-500/20',
                  !canGuard && 'ml-auto'
                )}
              >
                Strike {attack.opponent_name}
              </button>
            )}
          </div>
        );
      })}
    </div>
  );
}

/**
 * DuelChallengeControls — duel-specific affordances for the combat rail.
 *
 * Two independent components surfaced by CombatTurnPanel when relevant, plus the
 * shared `registryRef` dispatch helper:
 *
 * 1. DuelYieldControls — Yield button shown while an active duel is in progress.
 *    Dispatches registry action 'yield'. Guards on `isActiveDuel` (caller derives
 *    this from encounter.encounter_type === 'duel' && encounter.status !== 'completed').
 *
 * 2. DuelAcknowledgeRiskBanner — Full-width warning shown when the encounter is
 *    lethal (encounter.is_lethal) and the character has not yet acknowledged risk.
 *    Dispatches registry action 'acknowledge_risk'. Caller derives `showBanner`
 *    from encounter.is_lethal (backend sets this; acknowledgement state is opaque
 *    to the frontend; the backend removes this action from availability once acked).
 *
 * Both components dispatch through useDispatchPlayerAction (the same hook used by
 * YourTurn for combat actions), and both check `isDispatchFailure(result)` before
 * flipping confirmed local state — the dispatch endpoint resolves HTTP 200 with
 * `success: false` for a business-rule rejection (#2423).
 *
 * The Accept/Decline prompt for an incoming pending challenge (formerly
 * DuelChallengeControls here) lives in DuelChallengeNotifier's toast body since
 * #2157 — the standalone in-panel prompt was superseded and was deleted (#2423).
 * `registryRef` is re-exported from here for that caller.
 *
 * Part of #568 — Duels feature, Task 14. Inbox wiring + challenge_id threading: #1180.
 */

import { useState } from 'react';
import { cn } from '@/lib/utils';
import { useDispatchPlayerAction } from '@/combat/queries';
import { isDispatchFailure } from '@/combat/types';

// ---------------------------------------------------------------------------
// Dispatch helper — registry-backend action with no extra kwargs
// ---------------------------------------------------------------------------

export function registryRef(key: string, kwargs: Record<string, unknown> = {}) {
  return {
    ref: {
      backend: 'registry' as const,
      registry_key: key,
    },
    kwargs,
  };
}

// ---------------------------------------------------------------------------
// DuelYieldControls — Yield button
// ---------------------------------------------------------------------------

export interface DuelYieldControlsProps {
  /** The character performing the action. */
  characterId: number;
  /**
   * True when the character is an active participant in a non-completed duel.
   * Caller derives: encounter.encounter_type === 'duel' && encounter.status !== 'completed'
   * && encounter.is_participant.
   */
  isActiveDuel: boolean;
}

/**
 * Yield button shown during an active duel.
 *
 * Renders null when `isActiveDuel` is false. Shows a "yielded" confirmation
 * state after the dispatch succeeds (prevents double-fire).
 */
export function DuelYieldControls({ characterId, isActiveDuel }: DuelYieldControlsProps) {
  const { mutateAsync, isPending } = useDispatchPlayerAction(characterId);
  const [yielded, setYielded] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!isActiveDuel) return null;

  async function handleYield() {
    setError(null);
    try {
      const result = await mutateAsync(registryRef('yield'));
      if (isDispatchFailure(result)) {
        setError(result.message ?? 'Failed to yield');
        return;
      }
      setYielded(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to yield');
    }
  }

  return (
    <div className="space-y-2" data-testid="duel-yield-section">
      <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Duel</p>

      {yielded ? (
        <div
          className="rounded-md border border-muted-foreground/40 bg-muted px-3 py-2 text-center text-sm text-muted-foreground"
          data-testid="duel-yield-confirmed"
        >
          You have yielded the duel.
        </div>
      ) : (
        <button
          type="button"
          disabled={isPending}
          onClick={() => {
            handleYield().catch(() => {});
          }}
          data-testid="duel-yield-btn"
          className={cn(
            'w-full rounded-md border px-4 py-2 text-sm font-semibold transition-colors',
            'disabled:cursor-not-allowed disabled:opacity-50',
            isPending
              ? 'border-border bg-muted text-muted-foreground'
              : 'border-amber-500/60 bg-amber-500/10 text-amber-300 hover:bg-amber-500/20'
          )}
        >
          {isPending ? 'Yielding…' : 'Yield Duel'}
        </button>
      )}

      {error !== null && (
        <p role="alert" className="text-sm text-destructive" data-testid="duel-yield-error">
          {error}
        </p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// DuelAcknowledgeRiskBanner — lethal risk acknowledgement
// ---------------------------------------------------------------------------

export interface DuelAcknowledgeRiskBannerProps {
  /** The character performing the action. */
  characterId: number;
  /**
   * True when the duel is lethal and the character has not yet acknowledged risk.
   * Caller derives from encounter.is_lethal (once acknowledged, the backend removes
   * the acknowledge_risk action from the available actions list — the caller can
   * optionally re-derive from that signal).
   */
  showBanner: boolean;
}

/**
 * Full-width lethal-risk acknowledgement banner shown at the top of the duel rail.
 *
 * Renders null when `showBanner` is false.
 * Dispatches 'acknowledge_risk' on click; hides itself after success.
 */
export function DuelAcknowledgeRiskBanner({
  characterId,
  showBanner,
}: DuelAcknowledgeRiskBannerProps) {
  const { mutateAsync, isPending } = useDispatchPlayerAction(characterId);
  const [acknowledged, setAcknowledged] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!showBanner || acknowledged) return null;

  async function handleAcknowledge() {
    setError(null);
    try {
      const result = await mutateAsync(registryRef('acknowledge_risk'));
      if (isDispatchFailure(result)) {
        setError(result.message ?? 'Failed to acknowledge risk');
        return;
      }
      setAcknowledged(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to acknowledge risk');
    }
  }

  return (
    <div
      className="space-y-2 rounded-md border border-destructive/60 bg-destructive/10 p-3"
      data-testid="duel-acknowledge-risk-banner"
    >
      <p className="text-xs font-semibold uppercase tracking-wide text-destructive">
        Lethal Duel — Risk Acknowledgement Required
      </p>
      <p className="text-sm text-foreground">
        This duel carries lethal consequences. You must acknowledge the risk before declaring
        actions.
      </p>

      <button
        type="button"
        disabled={isPending}
        onClick={() => {
          handleAcknowledge().catch(() => {});
        }}
        data-testid="duel-acknowledge-risk-btn"
        className={cn(
          'w-full rounded-md border px-4 py-2 text-sm font-semibold transition-colors',
          'disabled:cursor-not-allowed disabled:opacity-50',
          isPending
            ? 'border-border bg-muted text-muted-foreground'
            : 'border-destructive bg-destructive/20 text-destructive hover:bg-destructive/30'
        )}
      >
        {isPending ? 'Acknowledging…' : 'I Acknowledge the Risk'}
      </button>

      {error !== null && (
        <p role="alert" className="text-sm text-destructive" data-testid="duel-acknowledge-error">
          {error}
        </p>
      )}
    </div>
  );
}

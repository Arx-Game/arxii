/**
 * DuelChallengeControls — duel-specific affordances for the combat rail.
 *
 * Three independent components surfaced by CombatTurnPanel when relevant:
 *
 * 1. DuelChallengeControls — Accept/Decline prompt for an incoming pending challenge.
 *    Driven by the GET /api/combat/duel-challenges/ inbox (#1180): the caller fetches
 *    the inbox, finds the incoming challenge for this character, and passes
 *    `hasPendingIncomingChallenge`, `challengerName`, and the specific `challengeId`.
 *    Dispatches registry actions 'accept' / 'decline' (threading `challenge_id`) via
 *    useDispatchPlayerAction.
 *
 * 2. DuelYieldControls — Yield button shown while an active duel is in progress.
 *    Dispatches registry action 'yield'. Guards on `isActiveDuel` (caller derives
 *    this from encounter.encounter_type === 'duel' && encounter.status !== 'completed').
 *
 * 3. DuelAcknowledgeRiskBanner — Full-width warning shown when the encounter is
 *    lethal (encounter.is_lethal) and the character has not yet acknowledged risk.
 *    Dispatches registry action 'acknowledge_risk'. Caller derives `showBanner`
 *    from encounter.is_lethal (backend sets this; acknowledgement state is opaque
 *    to the frontend; the backend removes this action from availability once acked).
 *
 * All three components dispatch through useDispatchPlayerAction (the same hook
 * used by YourTurn for combat actions).
 *
 * Part of #568 — Duels feature, Task 14. Inbox wiring + challenge_id threading: #1180.
 */

import { useState } from 'react';
import { cn } from '@/lib/utils';
import { useDispatchPlayerAction } from '@/combat/queries';

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
// DuelChallengeControls — Accept / Decline prompt
// ---------------------------------------------------------------------------

export interface DuelChallengeControlsProps {
  /** The character performing the action (used by useDispatchPlayerAction). */
  characterId: number;
  /** True when this character has a PENDING incoming DuelChallenge. */
  hasPendingIncomingChallenge: boolean;
  /** Display name of the challenger — shown in the prompt. */
  challengerName: string | null;
  /**
   * The specific PENDING challenge this prompt acts on. Threaded into the action
   * kwargs as `challenge_id` so accept/decline target the intended challenge when
   * a PC has more than one pending (#1180). Null when unknown (back-compat).
   */
  challengeId?: number | null;
  /**
   * Called after a successful accept/decline so the caller can refresh caches
   * (e.g. invalidate the inbox + the scene's active-encounter list).
   */
  onResolved?: () => void;
}

/**
 * Accept/Decline prompt for an incoming duel challenge.
 *
 * Renders null when `hasPendingIncomingChallenge` is false.
 * Dispatches the 'accept' or 'decline' registry action (threading `challenge_id`)
 * on click. The caller supplies the availability + identity from the
 * GET /api/combat/duel-challenges/ inbox (#1180).
 */
export function DuelChallengeControls({
  characterId,
  hasPendingIncomingChallenge,
  challengerName,
  challengeId = null,
  onResolved,
}: DuelChallengeControlsProps) {
  const { mutateAsync, isPending } = useDispatchPlayerAction(characterId);
  const [error, setError] = useState<string | null>(null);

  if (!hasPendingIncomingChallenge) return null;

  const challengeKwargs: Record<string, unknown> =
    challengeId != null ? { challenge_id: challengeId } : {};

  async function handleAccept() {
    setError(null);
    try {
      await mutateAsync(registryRef('accept', challengeKwargs));
      onResolved?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to accept challenge');
    }
  }

  async function handleDecline() {
    setError(null);
    try {
      await mutateAsync(registryRef('decline', challengeKwargs));
      onResolved?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to decline challenge');
    }
  }

  return (
    <div
      className="space-y-2 rounded-md border border-amber-500/50 bg-amber-500/10 p-3"
      data-testid="duel-challenge-prompt"
    >
      <p className="text-xs font-semibold uppercase tracking-wide text-amber-300">Duel Challenge</p>
      <p className="text-sm text-foreground">
        {challengerName ? (
          <>
            <span className="font-semibold">{challengerName}</span> has challenged you to a duel.
          </>
        ) : (
          'You have received a duel challenge.'
        )}
      </p>

      <div className="flex gap-2">
        <button
          type="button"
          disabled={isPending}
          onClick={() => {
            handleAccept().catch(() => {});
          }}
          data-testid="duel-accept-btn"
          className={cn(
            'flex-1 rounded-md border px-3 py-1.5 text-sm font-semibold transition-colors',
            'disabled:cursor-not-allowed disabled:opacity-50',
            isPending
              ? 'border-border bg-muted text-muted-foreground'
              : 'border-emerald-500/60 bg-emerald-500/10 text-emerald-300 hover:bg-emerald-500/20'
          )}
        >
          {isPending ? 'Dispatching…' : 'Accept'}
        </button>

        <button
          type="button"
          disabled={isPending}
          onClick={() => {
            handleDecline().catch(() => {});
          }}
          data-testid="duel-decline-btn"
          className={cn(
            'flex-1 rounded-md border px-3 py-1.5 text-sm font-semibold transition-colors',
            'disabled:cursor-not-allowed disabled:opacity-50',
            isPending
              ? 'border-border bg-muted text-muted-foreground'
              : 'border-destructive/60 bg-destructive/10 text-destructive hover:bg-destructive/20'
          )}
        >
          {isPending ? 'Dispatching…' : 'Decline'}
        </button>
      </div>

      {error !== null && (
        <p role="alert" className="text-sm text-destructive" data-testid="duel-challenge-error">
          {error}
        </p>
      )}
    </div>
  );
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
      await mutateAsync(registryRef('yield'));
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
      await mutateAsync(registryRef('acknowledge_risk'));
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

/**
 * DuelWithdrawNotifier — site-wide persistent prompt for an outgoing duel
 * challenge the player can retract (#3381, issue story 8).
 *
 * Mirrors `DuelChallengeNotifier`'s structure (mounted once at the app root,
 * polls `useDuelChallengeInbox`, fires one toast per newly-seen challenge id)
 * but for the OUTGOING side (`role: 'outgoing'`) and with a persistent
 * (`duration: Infinity`) toast — mirrors `HazardPromptNotifier`'s pattern for
 * a prompt that isn't dismissed by reading it.
 *
 * Mount point (deliberately verified against code, per #3381's spec note
 * asking to check this at implementation time rather than assume the combat
 * rail): a `DuelChallenge` has no `CombatEncounter` until `accept_challenge()`
 * runs (`world/combat/duels.py`), so `CombatRail`/`CombatTurnPanel` — which
 * `SceneDetailPage` only mounts once an *active encounter* exists — never
 * renders for the challenger in the window between issuing a challenge and it
 * being accepted/declined/expired. That's exactly the window a withdraw
 * affordance needs to be visible in, so embedding it in the rail (as the
 * spec's first-listed option) would never actually show it for the primary
 * use case. Site-wide, alongside `DuelChallengeNotifier`, is the only mount
 * point that covers it.
 *
 * Unlike an incoming-challenge toast (dismissed only by the player's own
 * Accept/Decline click), an outgoing challenge can also resolve on the OTHER
 * side — this toast is also dismissed automatically once its id no longer
 * appears in the outgoing PENDING poll (accepted/declined/expired elsewhere),
 * in addition to dismissing on a successful Withdraw click.
 *
 * Renders nothing itself — `null` always, purely a side-effect component.
 */

import { useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';
import { useMyRosterEntriesQuery } from '@/roster/queries';
import type { MyRosterEntry } from '@/roster/types';
import { useDuelChallengeInbox, useDispatchPlayerAction } from './queries';
import type { DuelChallenge } from './api';
import { registryRef } from './duels/DuelChallengeControls';
import { isDispatchFailure } from '@/combat/types';

interface ToastBodyProps {
  toastId: string | number;
  challenge: DuelChallenge;
  characterId: number;
  characterName: string;
}

function DuelWithdrawToastBody({ toastId, challenge, characterId, characterName }: ToastBodyProps) {
  const { mutateAsync } = useDispatchPlayerAction(characterId);
  const [isPending, setIsPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleWithdraw() {
    setIsPending(true);
    setError(null);
    try {
      const result = await mutateAsync(registryRef('withdraw', { challenge_id: challenge.id }));
      if (isDispatchFailure(result)) {
        setError(result.message ?? 'Failed to withdraw the challenge.');
        return;
      }
      toast.dismiss(toastId);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to withdraw the challenge.');
    } finally {
      setIsPending(false);
    }
  }

  return (
    <div
      className="rounded-md border border-border bg-card p-3 shadow-sm"
      data-testid="duel-withdraw-toast"
    >
      <p className="text-sm text-foreground">
        Your duel challenge to <span className="font-semibold">{challenge.challenged.name}</span> is
        pending.
      </p>
      <p className="mt-1 text-xs text-muted-foreground">
        Issued as <span className="font-semibold">{characterName}</span>.
      </p>
      <div className="mt-2">
        <button
          type="button"
          disabled={isPending}
          onClick={() => {
            handleWithdraw().catch(() => {});
          }}
          data-testid="duel-withdraw-toast-btn"
          className="rounded border border-destructive/60 bg-destructive/10 px-3 py-1 text-xs font-semibold text-destructive disabled:cursor-not-allowed disabled:opacity-50"
        >
          {isPending ? 'Withdrawing…' : 'Withdraw Challenge'}
        </button>
      </div>
      {error !== null && (
        <p
          role="alert"
          className="mt-2 text-xs text-destructive"
          data-testid="duel-withdraw-toast-error"
        >
          {error}
        </p>
      )}
    </div>
  );
}

/**
 * Resolve the roster entry for the CharacterSheet id the challenge was issued
 * by. Returns null for a `challenger: null` row (a GM-initiated lethal duel
 * proposal, #3068) — that can't appear under `role=outgoing` for a PC (the
 * filter scopes to `challenger_sheet_id in played_ids`), but the null check
 * keeps this defensive rather than assuming the server-side invariant holds.
 */
function resolveChallenger(
  challenge: DuelChallenge,
  myRosterEntries: MyRosterEntry[]
): { characterId: number; characterName: string } | null {
  if (challenge.challenger === null) return null;
  const challengerId = challenge.challenger.id;
  const challengerName = challenge.challenger.name;
  const entry = myRosterEntries.find((e) => e.character_id === challengerId);
  return {
    characterId: entry?.character_id ?? challengerId,
    characterName: entry?.name ?? challengerName,
  };
}

export function DuelWithdrawNotifier() {
  const { data: myRosterEntries = [] } = useMyRosterEntriesQuery();

  const { data: outgoingChallenges = [] } = useDuelChallengeInbox({
    enabled: myRosterEntries.length > 0,
    role: 'outgoing',
  });

  const toastedIds = useRef<Map<number, string | number>>(new Map());

  useEffect(() => {
    const currentIds = new Set(outgoingChallenges.map((c) => c.id));

    // Dismiss toasts for challenges that dropped out of the PENDING outgoing
    // list since the last poll (accepted/declined/expired on the other side)
    // without the player clicking Withdraw here.
    for (const [id, toastId] of toastedIds.current.entries()) {
      if (!currentIds.has(id)) {
        toast.dismiss(toastId);
        toastedIds.current.delete(id);
      }
    }

    for (const challenge of outgoingChallenges) {
      if (toastedIds.current.has(challenge.id)) continue;
      const resolved = resolveChallenger(challenge, myRosterEntries);
      if (resolved === null) continue;

      const toastId = toast.custom(
        (id) => (
          <DuelWithdrawToastBody
            toastId={id}
            challenge={challenge}
            characterId={resolved.characterId}
            characterName={resolved.characterName}
          />
        ),
        { duration: Infinity }
      );
      toastedIds.current.set(challenge.id, toastId);
    }
  }, [outgoingChallenges, myRosterEntries]);

  return null;
}

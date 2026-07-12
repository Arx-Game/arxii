/**
 * DuelChallengeNotifier — site-wide alert for an incoming duel challenge (#2157).
 *
 * `useDuelChallengeInbox` was previously polled only inside `CombatScenePage`,
 * so a player who never navigated there never saw an incoming challenge. This
 * component is mounted once at the app root (alongside `<Toaster/>` and
 * `<RouletteModal/>` in App.tsx) and fires a toast — with inline Accept/Decline
 * buttons — the first time a new challenge id appears in the poll. A `Set` of
 * already-toasted ids prevents the 15s poll from re-firing the same toast.
 *
 * Accept/Decline await the dispatch (mirroring DuelChallengeControls' mutateAsync
 * + try/catch pattern) — the toast only dismisses on success; on failure it stays
 * open with an inline error and the buttons remain clickable to retry, so a failed
 * dispatch is never silently lost (the id was already added to toastedIds when the
 * toast first fired, so a dismissed-on-error toast would otherwise never resurface).
 *
 * Right-character dispatch (#2166): `useDuelChallengeInbox` is already account-wide
 * (server-scoped to `request.user.played_character_sheet_ids`, not the active
 * character), so a challenge addressed to a *background* character can appear
 * while a different character is active. Each toast resolves the challenged
 * character's own roster entry (`challenge.challenged.id` is the CharacterSheet
 * pk, matching `MyRosterEntry.character_id`) and dispatches Accept/Decline as
 * THAT character — never the active one. Resolution + the `useDispatchPlayerAction`
 * call both live in `DuelChallengeToastBody` (one component instance per toast, its
 * own hook call bound to the resolved character id) rather than the notifier's
 * top level, because a single top-level hook call can only bind one fixed
 * character and multiple background challenges may target different characters
 * concurrently. The dispatch is plain REST by character id
 * (`POST /api/actions/characters/{characterId}/dispatch/`) — it works whether or
 * not that character has a live session/tab open.
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

interface ToastBodyProps {
  toastId: string | number;
  challenge: DuelChallenge;
  /** The challenged character's own sheet id — dispatch always uses this, never the active character. */
  characterId: number;
  characterName: string;
}

function DuelChallengeToastBody({
  toastId,
  challenge,
  characterId,
  characterName,
}: ToastBodyProps) {
  const { mutateAsync } = useDispatchPlayerAction(characterId);
  const [isPending, setIsPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handle(action: 'accept' | 'decline') {
    setIsPending(true);
    setError(null);
    try {
      await mutateAsync(registryRef(action, { challenge_id: challenge.id }));
      toast.dismiss(toastId);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to respond to the challenge');
    } finally {
      setIsPending(false);
    }
  }

  return (
    <div
      className="rounded-md border border-amber-500/50 bg-amber-500/10 p-3 shadow-sm"
      data-testid="duel-challenge-toast"
    >
      <p className="text-sm text-foreground">
        <span className="font-semibold">{challenge.challenger.name}</span> has challenged{' '}
        <span className="font-semibold">{characterName}</span> to a duel.
      </p>
      <p className="mt-1 text-xs text-muted-foreground">
        Responding as <span className="font-semibold">{characterName}</span>.
      </p>
      <div className="mt-2 flex gap-2">
        <button
          type="button"
          disabled={isPending}
          onClick={() => {
            handle('accept').catch(() => {});
          }}
          data-testid="duel-toast-accept-btn"
          className="rounded border border-emerald-500/60 bg-emerald-500/10 px-3 py-1 text-xs font-semibold text-emerald-300 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {isPending ? 'Dispatching…' : 'Accept'}
        </button>
        <button
          type="button"
          disabled={isPending}
          onClick={() => {
            handle('decline').catch(() => {});
          }}
          data-testid="duel-toast-decline-btn"
          className="rounded border border-destructive/60 bg-destructive/10 px-3 py-1 text-xs font-semibold text-destructive disabled:cursor-not-allowed disabled:opacity-50"
        >
          {isPending ? 'Dispatching…' : 'Decline'}
        </button>
      </div>
      {error !== null && (
        <p role="alert" className="mt-2 text-xs text-destructive" data-testid="duel-toast-error">
          {error}
        </p>
      )}
    </div>
  );
}

/** Resolve the roster entry (if any) for the CharacterSheet id the challenge is addressed to. */
function resolveChallenged(
  challenge: DuelChallenge,
  myRosterEntries: MyRosterEntry[]
): { characterId: number; characterName: string } {
  const entry = myRosterEntries.find((e) => e.character_id === challenge.challenged.id);
  return {
    characterId: entry?.character_id ?? challenge.challenged.id,
    characterName: entry?.name ?? challenge.challenged.name,
  };
}

export function DuelChallengeNotifier() {
  const { data: myRosterEntries = [] } = useMyRosterEntriesQuery();

  const { data: incomingChallenges = [] } = useDuelChallengeInbox({
    enabled: myRosterEntries.length > 0,
    role: 'incoming',
  });

  const toastedIds = useRef<Set<number>>(new Set());

  useEffect(() => {
    for (const challenge of incomingChallenges) {
      if (toastedIds.current.has(challenge.id)) continue;
      toastedIds.current.add(challenge.id);

      const { characterId, characterName } = resolveChallenged(challenge, myRosterEntries);

      toast.custom((toastId) => (
        <DuelChallengeToastBody
          toastId={toastId}
          challenge={challenge}
          characterId={characterId}
          characterName={characterName}
        />
      ));
    }
  }, [incomingChallenges, myRosterEntries]);

  return null;
}

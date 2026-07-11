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
 * Renders nothing itself — `null` always, purely a side-effect component.
 */

import { useEffect, useMemo, useRef, useState } from 'react';
import { toast } from 'sonner';
import { useAppSelector } from '@/store/hooks';
import { useMyRosterEntriesQuery } from '@/roster/queries';
import { useDuelChallengeInbox, useDispatchPlayerAction } from './queries';
import { registryRef } from './duels/DuelChallengeControls';

interface ToastBodyProps {
  challengerName: string;
  onAccept: () => Promise<void>;
  onDecline: () => Promise<void>;
}

function DuelChallengeToastBody({ challengerName, onAccept, onDecline }: ToastBodyProps) {
  const [isPending, setIsPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handle(action: () => Promise<void>) {
    setIsPending(true);
    setError(null);
    try {
      await action();
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
        <span className="font-semibold">{challengerName}</span> has challenged you to a duel.
      </p>
      <div className="mt-2 flex gap-2">
        <button
          type="button"
          disabled={isPending}
          onClick={() => {
            handle(onAccept).catch(() => {});
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
            handle(onDecline).catch(() => {});
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

export function DuelChallengeNotifier() {
  const activeCharacter = useAppSelector((state) => state.game.active);
  const { data: myRosterEntries = [] } = useMyRosterEntriesQuery();
  const activeEntry = useMemo(
    () => myRosterEntries.find((e) => e.name === activeCharacter) ?? null,
    [myRosterEntries, activeCharacter]
  );
  const characterId = activeEntry?.character_id ?? 0;

  const { data: incomingChallenges = [] } = useDuelChallengeInbox({
    enabled: characterId > 0,
    role: 'incoming',
  });
  const { mutateAsync } = useDispatchPlayerAction(characterId);

  const toastedIds = useRef<Set<number>>(new Set());

  useEffect(() => {
    for (const challenge of incomingChallenges) {
      if (toastedIds.current.has(challenge.id)) continue;
      toastedIds.current.add(challenge.id);

      toast.custom((toastId) => (
        <DuelChallengeToastBody
          challengerName={challenge.challenger.name}
          onAccept={async () => {
            await mutateAsync(registryRef('accept', { challenge_id: challenge.id }));
            toast.dismiss(toastId);
          }}
          onDecline={async () => {
            await mutateAsync(registryRef('decline', { challenge_id: challenge.id }));
            toast.dismiss(toastId);
          }}
        />
      ));
    }
  }, [incomingChallenges, mutateAsync]);

  return null;
}

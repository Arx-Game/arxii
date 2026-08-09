/**
 * SummonPromptNotifier — site-wide consent prompt for a GM summon (#3071).
 *
 * Mirrors `DuelChallengeNotifier` (`@/combat/DuelChallengeNotifier`): mounted once
 * at the app root, polls `useSummonOfferInbox`, and fires a toast with inline
 * Accept/Decline buttons the first time a new offer id appears. A `Set` of
 * already-toasted ids prevents the 15s poll from re-firing the same toast.
 *
 * Leak analysis (spec-approved): the toast names the GM (`gm_display_name`) and
 * the scene title only — never room contents or other occupants — so a decline
 * reveals nothing further.
 *
 * Accept/Decline dispatch through the generic REGISTRY action-dispatch endpoint
 * (`accept_gm_summon` / `decline_gm_summon`), the same seam `DuelChallengeControls`
 * uses via `registryRef` — awaited with `isDispatchFailure` handling (#2423) so a
 * business-rule rejection stays inline and retryable rather than silently
 * dismissing the toast.
 *
 * Renders nothing itself — `null` always, purely a side-effect component.
 */

import { useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';
import { useDispatchPlayerAction } from '@/combat/queries';
import { registryRef } from '@/combat/duels/DuelChallengeControls';
import { isDispatchFailure } from '@/combat/types';
import { useMyRosterEntriesQuery } from '@/roster/queries';
import type { MyRosterEntry } from '@/roster/types';
import { useSummonOfferInbox } from './queries';
import type { GMSummonOfferEntry } from './types';

interface ToastBodyProps {
  toastId: string | number;
  offer: GMSummonOfferEntry;
  characterId: number;
  characterName: string;
}

function SummonToastBody({ toastId, offer, characterId, characterName }: ToastBodyProps) {
  const { mutateAsync } = useDispatchPlayerAction(characterId);
  const [isPending, setIsPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handle(action: 'accept_gm_summon' | 'decline_gm_summon') {
    setIsPending(true);
    setError(null);
    try {
      const result = await mutateAsync(registryRef(action, {}));
      if (isDispatchFailure(result)) {
        setError(result.message ?? 'Failed to respond to the summons');
        return;
      }
      toast.dismiss(toastId);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to respond to the summons');
    } finally {
      setIsPending(false);
    }
  }

  const gmName = offer.gm_display_name || 'A GM';
  const sceneTitle = offer.scene_title ?? 'their scene';

  return (
    <div
      className="rounded-md border border-amber-500/50 bg-amber-500/10 p-3 shadow-sm"
      data-testid="summon-prompt-toast"
    >
      <p className="text-sm text-foreground">
        <span className="font-semibold">{gmName}</span> has invited{' '}
        <span className="font-semibold">{characterName}</span> to join{' '}
        <span className="font-semibold">{sceneTitle}</span>.
      </p>
      <div className="mt-2 flex gap-2">
        <button
          type="button"
          disabled={isPending}
          onClick={() => {
            handle('accept_gm_summon').catch(() => {});
          }}
          data-testid="summon-toast-accept-btn"
          className="rounded border border-emerald-500/60 bg-emerald-500/10 px-3 py-1 text-xs font-semibold text-emerald-300 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {isPending ? 'Dispatching…' : 'Accept'}
        </button>
        <button
          type="button"
          disabled={isPending}
          onClick={() => {
            handle('decline_gm_summon').catch(() => {});
          }}
          data-testid="summon-toast-decline-btn"
          className="rounded border border-destructive/60 bg-destructive/10 px-3 py-1 text-xs font-semibold text-destructive disabled:cursor-not-allowed disabled:opacity-50"
        >
          {isPending ? 'Dispatching…' : 'Decline'}
        </button>
      </div>
      {error !== null && (
        <p role="alert" className="mt-2 text-xs text-destructive" data-testid="summon-toast-error">
          {error}
        </p>
      )}
    </div>
  );
}

/** Resolve the roster entry (if any) for the CharacterSheet id the summon is addressed to. */
function resolveTarget(
  offer: GMSummonOfferEntry,
  myRosterEntries: MyRosterEntry[]
): { characterId: number; characterName: string } {
  const entry = myRosterEntries.find((e) => e.character_id === offer.target_character_id);
  return {
    characterId: entry?.character_id ?? offer.target_character_id,
    characterName: entry?.name ?? 'your character',
  };
}

export function SummonPromptNotifier() {
  const { data: myRosterEntries = [] } = useMyRosterEntriesQuery();

  const { data: pendingOffers = [] } = useSummonOfferInbox({
    enabled: myRosterEntries.length > 0,
  });

  const toastedIds = useRef<Set<number>>(new Set());

  useEffect(() => {
    for (const offer of pendingOffers) {
      if (toastedIds.current.has(offer.id)) continue;
      toastedIds.current.add(offer.id);

      const { characterId, characterName } = resolveTarget(offer, myRosterEntries);

      toast.custom((toastId) => (
        <SummonToastBody
          toastId={toastId}
          offer={offer}
          characterId={characterId}
          characterName={characterName}
        />
      ));
    }
  }, [pendingOffers, myRosterEntries]);

  return null;
}

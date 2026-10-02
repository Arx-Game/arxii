/**
 * UltimateRevealGate — mounts in the combat panel; polls the owner's Audere
 * ultimate state while a ceremony runs, auto-opens UltimateRevealDialog once
 * per reveal, and renders the deferred-death banner whenever the backend
 * carries one (#4098).
 *
 * The endpoint is cheap to call even when no ceremony is active (reveal and
 * readied both come back null, deferred_death_text empty) — polling is still
 * gated by `isCeremonyActive` so the panel doesn't poll it constantly.
 */

import { useEffect, useState } from 'react';
import { Flame } from 'lucide-react';
import { useAudereUltimates, useChooseUltimate } from '@/magic/queries';
import { useAutoOpenOncePerOffer } from '@/magic/hooks';
import { UltimateRevealDialog } from './UltimateRevealDialog';
import type { ReadiedUltimate, UltimateReveal } from '@/magic/types';

interface UltimateRevealGateProps {
  characterSheetId: number;
  characterId: number;
  encounterId: number;
  isCeremonyActive: boolean;
}

export function UltimateRevealGate({
  characterSheetId,
  characterId,
  encounterId,
  isCeremonyActive,
}: UltimateRevealGateProps) {
  const { data } = useAudereUltimates(characterSheetId, isCeremonyActive);
  const choose = useChooseUltimate(characterSheetId, characterId, encounterId);
  const [chosen, setChosen] = useState<ReadiedUltimate | null>(null);

  // Remembers the last non-null reveal so the Screen 3 confirmation has
  // chrome (ceremony/groups shape) to render from once the poll right after
  // a choice answers with `reveal: null` (fix round 1 item 1).
  const [lastReveal, setLastReveal] = useState<UltimateReveal | null>(null);
  useEffect(() => {
    if (data?.reveal) setLastReveal(data.reveal);
  }, [data?.reveal]);

  // A new set of groups/cards (by choice_key) is a new reveal worth
  // re-prompting for; this also keys the auto-open below. Once a choice
  // lands, the backend's next poll answers with `reveal: null`, so this
  // key goes back to null WITHOUT representing "a new reveal" — the shared
  // hook only re-opens on a genuinely new, non-null key, so it won't reopen
  // just because the reveal cleared.
  const revealKey = data?.reveal
    ? data.reveal.groups.map((g) => g.cards.map((c) => c.choice_key).join()).join('|')
    : null;

  // Auto-open once per reveal (shared with AudereOfferGate/AudereMajoraOfferGate).
  const { dialogOpen: open, setDialogOpen: setOpen } = useAutoOpenOncePerOffer(revealKey);

  // Clear any previously chosen card once a genuinely new reveal arrives
  // (not on the reveal clearing to null after a choice — the confirmation
  // must survive that transition, see below).
  useEffect(() => {
    if (revealKey) setChosen(null);
  }, [revealKey]);

  const readied = chosen ?? data?.readied ?? null;
  // Confirmation (Screen 3) mounts on EITHER a live reveal OR a just-chosen
  // card, using `lastReveal` for chrome once the live reveal has cleared —
  // without this the dialog (and its "Ultimate ready" strip after dismissal)
  // both go missing right after a real choice (fix round 1 item 1).
  const reveal = data?.reveal ?? lastReveal;
  const showDialog = Boolean(reveal) && Boolean(data?.reveal || chosen);

  return (
    <>
      {data?.deferred_death_text ? (
        <div
          role="alert"
          data-testid="deferred-death-banner"
          className="rounded-md border border-red-600/60 bg-red-950/40 p-3 text-sm font-medium text-red-200"
        >
          {data.deferred_death_text}
        </div>
      ) : null}

      {readied && !open ? (
        <div
          data-testid="ultimate-ready-strip"
          className="rounded-md border border-fuchsia-500/60 bg-fuchsia-950/40 px-3 py-1.5 text-sm font-semibold text-fuchsia-300"
        >
          Ultimate ready: {readied.name}
        </div>
      ) : null}

      {data?.reveal && !readied && !open ? (
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="flex w-full animate-pulse items-center gap-2 rounded-md border border-fuchsia-500/60 bg-fuchsia-950/40 px-3 py-2 text-left text-sm font-semibold text-fuchsia-300 shadow-[0_0_24px_-8px] shadow-fuchsia-500/60 motion-reduce:animate-none"
          data-testid="ultimate-reveal-strip"
        >
          <Flame className="h-4 w-4 shrink-0" />
          Ultimates await: choose one
        </button>
      ) : null}

      {showDialog && reveal ? (
        <UltimateRevealDialog
          reveal={reveal}
          readied={readied}
          open={open}
          onOpenChange={(next) => {
            setOpen(next);
            if (!next) choose.reset();
          }}
          onChoose={(choiceKey) => {
            choose.mutate(
              { character_sheet_id: characterSheetId, choice_key: choiceKey },
              { onSuccess: (r) => setChosen(r) }
            );
          }}
          isPending={choose.isPending}
          errorMessage={
            choose.isError
              ? choose.error?.message ||
                'The choice did not land: your selection failed. Try again.'
              : null
          }
        />
      ) : null}
    </>
  );
}

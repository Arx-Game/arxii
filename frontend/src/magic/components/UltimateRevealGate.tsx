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
import { UltimateRevealDialog } from './UltimateRevealDialog';
import type { ReadiedUltimate } from '@/magic/types';

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
  const [open, setOpen] = useState(false);
  const [chosen, setChosen] = useState<ReadiedUltimate | null>(null);

  // Auto-open once per reveal: a new set of groups/cards (by choice_key) is a
  // new reveal worth re-prompting for.
  const revealKey = data?.reveal
    ? data.reveal.groups.map((g) => g.cards.map((c) => c.choice_key).join()).join('|')
    : null;

  useEffect(() => {
    if (revealKey) {
      setChosen(null);
      setOpen(true);
    }
  }, [revealKey]);

  const readied = chosen ?? data?.readied ?? null;

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

      {data?.reveal ? (
        <UltimateRevealDialog
          reveal={data.reveal}
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

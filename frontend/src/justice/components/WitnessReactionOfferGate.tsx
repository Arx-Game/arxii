/**
 * WitnessReactionOfferGate (#2987) - mounts in the scene panel; polls pending
 * witness reaction windows for the active persona, renders a call-out strip,
 * and auto-opens WitnessReactionDialog once per window id (re-openable from
 * the strip). Mirrors EntryFlourishOfferGate's structure, reusing
 * useAutoOpenOncePerOffer for the once-per-id dismissal bookkeeping.
 */

import { Eye } from 'lucide-react';
import { usePendingWitnessWindows, type PendingReactionWindow } from '@/justice/queries';
import { useAutoOpenOncePerOffer } from '@/magic/hooks';
import { WitnessReactionDialog } from './WitnessReactionDialog';

interface WitnessReactionOfferGateProps {
  personaId: number | null;
}

export function WitnessReactionOfferGate({ personaId }: WitnessReactionOfferGateProps) {
  // enabled guard: never poll without a resolved acting persona.
  const { data } = usePendingWitnessWindows(personaId != null);

  const windows = data?.results ?? [];
  const pendingWindow: PendingReactionWindow | null = windows[0] ?? null;

  // Auto-open once per window id; dismissing leaves the strip.
  const { dialogOpen, setDialogOpen } = useAutoOpenOncePerOffer(pendingWindow);

  if (!pendingWindow || personaId == null) return null;

  return (
    <>
      <button
        type="button"
        onClick={() => setDialogOpen(true)}
        className="flex w-full animate-pulse items-center gap-2 rounded-md border border-amber-500/60 bg-amber-950/40 px-3 py-2 text-left text-sm font-semibold text-amber-300 shadow-[0_0_24px_-8px] shadow-amber-500/60 motion-reduce:animate-none"
        data-testid="witness-reaction-gate-strip"
      >
        <Eye className="h-4 w-4 shrink-0" />
        React to something you witnessed
      </button>
      <WitnessReactionDialog
        pendingWindow={pendingWindow}
        personaId={personaId}
        open={dialogOpen}
        onOpenChange={(next) => setDialogOpen(next)}
        onClose={() => setDialogOpen(false)}
      />
    </>
  );
}

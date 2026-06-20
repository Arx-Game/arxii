/**
 * EntryFlourishOfferDialog — resonance picker for the entry-flourish ceremony.
 *
 * On scene entry the server emits a PendingEntryFlourishOffer; this dialog lets
 * the character declare which of their claimed resonances they broadcast to the
 * room. Chip style mirrors ReactionStrip. Mirrors AudereOfferDialog structure.
 */

import { useState } from 'react';
import { Sparkles } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { useCharacterResonances, useRespondToEntryFlourish } from '@/magic/queries';
import type { PendingEntryFlourishOffer } from '@/magic/types';

interface EntryFlourishOfferDialogProps {
  offer: PendingEntryFlourishOffer;
  characterSheetId: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onClose: () => void;
}

export function EntryFlourishOfferDialog({
  offer,
  characterSheetId,
  open,
  onOpenChange,
  onClose,
}: EntryFlourishOfferDialogProps) {
  const [selectedResonanceId, setSelectedResonanceId] = useState<number | null>(null);

  const { data: resonances = [], isLoading } = useCharacterResonances(characterSheetId);
  const respond = useRespondToEntryFlourish(characterSheetId);

  function handleConfirm() {
    if (selectedResonanceId == null) return;
    respond.mutate(
      { offer_id: offer.id, resonance_id: selectedResonanceId },
      {
        onSuccess: () => {
          setSelectedResonanceId(null);
          onClose();
        },
      }
    );
  }

  function handleOpenChange(next: boolean) {
    if (!next) {
      respond.reset();
    }
    onOpenChange(next);
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="border-emerald-500/60 shadow-[0_0_60px_-12px] shadow-emerald-500/50">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-2xl font-bold tracking-wide text-emerald-400">
            <Sparkles className="h-7 w-7" />
            Declare Your Resonance
          </DialogTitle>
          <DialogDescription className="text-base">
            Choose a resonance to broadcast as you enter the scene. Your declaration is felt by all
            present.
          </DialogDescription>
        </DialogHeader>

        {isLoading ? (
          <p className="text-sm text-muted-foreground" data-testid="entry-flourish-loading">
            Loading resonances…
          </p>
        ) : resonances.length === 0 ? (
          <p className="text-sm text-muted-foreground" data-testid="entry-flourish-empty">
            You have no claimed resonances to declare.
          </p>
        ) : (
          <div
            className="flex flex-wrap gap-2 rounded-md border border-emerald-500/30 bg-emerald-950/20 p-3"
            data-testid="entry-flourish-resonance-picker"
          >
            {resonances.map((cr) => {
              const isSelected = selectedResonanceId === cr.resonance;
              return (
                <button
                  key={cr.resonance}
                  type="button"
                  onClick={() => setSelectedResonanceId(cr.resonance)}
                  data-testid={`resonance-chip-${cr.resonance}`}
                  className={`rounded-full border px-3 py-1 text-sm transition-colors ${
                    isSelected
                      ? 'border-emerald-500 bg-emerald-500/20 font-semibold text-emerald-300'
                      : 'border-muted-foreground/30 text-muted-foreground hover:border-emerald-500/60 hover:text-emerald-300'
                  }`}
                >
                  {cr.resonance_name}
                </button>
              );
            })}
          </div>
        )}

        {respond.isError ? (
          <div
            role="alert"
            data-testid="entry-flourish-respond-error"
            className="rounded-md border border-red-600/60 bg-red-950/40 p-3 text-sm font-medium text-red-200"
          >
            {respond.error?.message || 'Your declaration did not land — please try again.'}
          </div>
        ) : null}

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={respond.isPending}>
            Not Yet
          </Button>
          <Button
            className="bg-emerald-600 text-white hover:bg-emerald-500"
            onClick={handleConfirm}
            disabled={selectedResonanceId == null || respond.isPending}
            data-testid="entry-flourish-confirm"
          >
            <Sparkles className="mr-1.5 h-4 w-4" />
            Declare
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

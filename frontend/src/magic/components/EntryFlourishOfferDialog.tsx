/**
 * EntryFlourishOfferDialog — resonance picker for the entry-flourish ceremony.
 *
 * On scene entry the server emits a PendingEntryFlourishOffer; this dialog lets
 * the character declare which resonance they broadcast to the room (#5308): any
 * resonance, the ones they hold first. Chip style mirrors ReactionStrip. Mirrors AudereOfferDialog structure.
 */

import { useMemo, useState } from 'react';
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
import {
  useCharacterResonances,
  useRespondToEntryFlourish,
  useResonanceCatalog,
} from '@/magic/queries';
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

  const { data: held = [], isLoading: heldLoading } = useCharacterResonances(characterSheetId);
  const { data: catalog = [], isLoading: catalogLoading } = useResonanceCatalog();
  const isLoading = heldLoading || catalogLoading;
  // Every resonance, the ones the character holds first.
  const resonances = useMemo(() => {
    const heldIds = new Set(held.map((cr) => cr.resonance));
    return [
      ...catalog.filter((resonance) => heldIds.has(resonance.id)),
      ...catalog.filter((resonance) => !heldIds.has(resonance.id)),
    ];
  }, [held, catalog]);
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

  const renderResonances = () => {
    if (isLoading) {
      return (
        <p className="text-sm text-muted-foreground" data-testid="entry-flourish-loading">
          Loading resonances…
        </p>
      );
    }
    if (resonances.length === 0) {
      return (
        <p className="text-sm text-muted-foreground" data-testid="entry-flourish-empty">
          No resonances.
        </p>
      );
    }
    return (
      <div
        className="flex flex-wrap gap-2 rounded-md border border-emerald-500/30 bg-emerald-950/20 p-3"
        data-testid="entry-flourish-resonance-picker"
      >
        {resonances.map((resonance) => {
          const isSelected = selectedResonanceId === resonance.id;
          return (
            <button
              key={resonance.id}
              type="button"
              onClick={() => setSelectedResonanceId(resonance.id)}
              data-testid={`resonance-chip-${resonance.id}`}
              className={`rounded-full border px-3 py-1 text-sm transition-colors ${
                isSelected
                  ? 'border-emerald-500 bg-emerald-500/20 font-semibold text-emerald-300'
                  : 'border-muted-foreground/30 text-muted-foreground hover:border-emerald-500/60 hover:text-emerald-300'
              }`}
            >
              {resonance.name}
            </button>
          );
        })}
      </div>
    );
  };

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

        {renderResonances()}

        {respond.isError ? (
          <div
            role="alert"
            data-testid="entry-flourish-respond-error"
            className="rounded-md border border-red-600/60 bg-red-950/40 p-3 text-sm font-medium text-red-200"
          >
            {respond.error?.message || 'Your declaration did not land; please try again.'}
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

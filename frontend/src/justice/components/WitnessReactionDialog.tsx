/**
 * WitnessReactionDialog (#2987) - the bystander reaction menu. Renders the
 * window's choices (report / intervene / ignore for the witness kind) as
 * plain, uncharacterized buttons; one tap posts the choice and closes.
 *
 * Deliberately shows NO reactor attribution and no other-witness state - the
 * payload carries none (witness reactions are anonymous end to end) and this
 * dialog must never grow any. Copy stays OOC and neutral: it presents the
 * choices without recommending or narrating a feeling for the player.
 * Mirrors EntryFlourishOfferDialog's structure.
 */

import { Eye } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { useReactToWindow, type PendingReactionWindow } from '@/justice/queries';

interface WitnessReactionDialogProps {
  pendingWindow: PendingReactionWindow;
  personaId: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onClose: () => void;
}

export function WitnessReactionDialog({
  pendingWindow,
  personaId,
  open,
  onOpenChange,
  onClose,
}: WitnessReactionDialogProps) {
  const react = useReactToWindow();

  function handleChoose(choice: string) {
    react.mutate(
      { windowId: pendingWindow.id, personaId, choice },
      {
        onSuccess: () => {
          onClose();
        },
      }
    );
  }

  function handleOpenChange(next: boolean) {
    if (!next) {
      react.reset();
    }
    onOpenChange(next);
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="border-amber-500/60 shadow-[0_0_60px_-12px] shadow-amber-500/50">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-2xl font-bold tracking-wide text-amber-400">
            <Eye className="h-7 w-7" />
            Witnessed Moment
          </DialogTitle>
          <DialogDescription className="text-base">
            Your character saw what just happened in this scene. Choose a response, or close this to
            decide later.
          </DialogDescription>
        </DialogHeader>

        <div
          className="flex flex-col gap-2 rounded-md border border-amber-500/30 bg-amber-950/20 p-3"
          data-testid="witness-reaction-choices"
        >
          {pendingWindow.choices.map((choice) => (
            <Button
              key={choice.slug}
              variant="outline"
              className="justify-start hover:border-amber-500/60 hover:text-amber-300"
              onClick={() => handleChoose(choice.slug)}
              disabled={react.isPending}
              data-testid={`witness-choice-${choice.slug}`}
            >
              {choice.label}
            </Button>
          ))}
        </div>

        {react.isError ? (
          <div
            role="alert"
            data-testid="witness-reaction-error"
            className="rounded-md border border-red-600/60 bg-red-950/40 p-3 text-sm font-medium text-red-200"
          >
            {react.error?.message || 'That reaction did not go through; please try again.'}
          </div>
        ) : null}

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={react.isPending}>
            Not Now
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

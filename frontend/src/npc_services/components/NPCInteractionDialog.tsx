import { useEffect, useState } from 'react';
import { toast } from 'sonner';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';

import {
  endInteraction,
  resolveOffer,
  startInteraction,
  type InteractionState,
} from '../interaction';

interface NPCInteractionDialogProps {
  roleId: number;
  /** Dialog heading, e.g. "Summon the Blighton representative". */
  title: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Fired after a final offer resolves (refetch the books). */
  onConcluded?: () => void;
}

/**
 * The generic summoned-NPC loop (#930): start an interaction with a role,
 * pick from its offer menu, watch results land, done. Backed by the
 * npc_services InteractionViewSet state machine (one in flight per session).
 */
export function NPCInteractionDialog({
  roleId,
  title,
  open,
  onOpenChange,
  onConcluded,
}: NPCInteractionDialogProps) {
  const [state, setState] = useState<InteractionState | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) {
      setState(null);
      return;
    }
    let cancelled = false;
    setBusy(true);
    startInteraction(roleId)
      .then((fresh) => {
        if (!cancelled) setState(fresh);
      })
      .catch((error: Error) => {
        toast.error(error.message);
        onOpenChange(false);
      })
      .finally(() => {
        if (!cancelled) setBusy(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- start once per open
  }, [open, roleId]);

  const close = (dialogOpen: boolean) => {
    if (!dialogOpen && state && !state.closed) {
      void endInteraction().catch(() => undefined);
    }
    onOpenChange(dialogOpen);
  };

  const pick = (offerId: number) => {
    setBusy(true);
    resolveOffer(offerId)
      .then((fresh) => {
        setState(fresh);
        if (fresh.last_result_message) {
          toast.success(fresh.last_result_message);
        }
        if (fresh.closed) {
          onConcluded?.();
        }
      })
      .catch((error: Error) => toast.error(error.message))
      .finally(() => setBusy(false));
  };

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>
            {state?.closed
              ? (state.last_result_message ?? 'The matter is settled.')
              : 'They hear you out.'}
          </DialogDescription>
        </DialogHeader>
        {busy && !state && <p className="text-sm text-muted-foreground">Sending for them…</p>}
        {state && !state.closed && (
          <div className="flex flex-col gap-2">
            {state.available_offers.length === 0 && (
              <p className="text-sm text-muted-foreground">
                They have nothing to offer you right now.
              </p>
            )}
            {state.available_offers.map((offer) => (
              <Button
                key={offer.id}
                variant="outline"
                className="justify-between"
                disabled={busy}
                onClick={() => pick(offer.id)}
              >
                <span>{offer.label}</span>
                {offer.is_final && <Badge variant="secondary">concludes</Badge>}
              </Button>
            ))}
          </div>
        )}
        {state?.closed && (
          <Button onClick={() => close(false)} className="self-end">
            Done
          </Button>
        )}
      </DialogContent>
    </Dialog>
  );
}

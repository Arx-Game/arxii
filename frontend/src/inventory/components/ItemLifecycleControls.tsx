/**
 * ItemLifecycleControls (#2886) — accent removal + recycling, both confirmed.
 *
 * UX rules:
 *   - Every accent row gets a small remove control; removal always confirms
 *     (irreversible, no refund — the crafter's work is gone for good).
 *   - Recycle always confirms (the item is destroyed for partial salvage).
 *   - A story-protected recycle attempt surfaces the GM-sign-off message and
 *     offers to file the request instead.
 */

import { useState } from 'react';
import { Recycle, X } from 'lucide-react';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Button, buttonVariants } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import {
  useRecycleItem,
  useRemoveAccent,
  useRequestRecycleApproval,
} from '../hooks/useItemLifecycle';
import type { ItemInstance } from '../types';

interface ItemLifecycleControlsProps {
  item: ItemInstance;
  /** Fired after a successful recycle so the parent can close the panel. */
  onRecycled?: () => void;
}

const GM_SIGNOFF_MARKER = 'GM must sign off';

export function ItemLifecycleControls({ item, onRecycled }: ItemLifecycleControlsProps) {
  const [removing, setRemoving] = useState<{ target: number; label: string } | null>(null);
  const [recycling, setRecycling] = useState(false);
  const [blockedMessage, setBlockedMessage] = useState<string | null>(null);
  const removeAccent = useRemoveAccent();
  const recycleItem = useRecycleItem();
  const requestApproval = useRequestRecycleApproval();

  const accents = item.accents ?? [];

  function handleConfirmRemove() {
    if (!removing) return;
    removeAccent.mutate({ itemId: item.id, accentTarget: removing.target });
    setRemoving(null);
  }

  function handleConfirmRecycle() {
    setRecycling(false);
    recycleItem.mutate(
      { itemId: item.id },
      {
        onSuccess: () => onRecycled?.(),
        onError: (error: Error) => {
          if (error.message.includes(GM_SIGNOFF_MARKER)) {
            setBlockedMessage(error.message);
          }
        },
      }
    );
  }

  function handleRequestSignoff() {
    if (blockedMessage !== null) {
      requestApproval.mutate({ itemId: item.id });
    }
    setBlockedMessage(null);
  }

  return (
    <div className="space-y-2">
      {accents.length > 0 && (
        <ul className="space-y-1">
          {accents.map((accent) => (
            <li key={accent.target} className="flex items-center justify-between text-sm">
              <span>
                {accent.adverb} {accent.adjective}
              </span>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                aria-label={`Remove ${accent.adjective} accent`}
                onClick={() => setRemoving({ target: accent.target, label: accent.adjective })}
                disabled={removeAccent.isPending}
              >
                <X className="h-3.5 w-3.5" />
              </Button>
            </li>
          ))}
        </ul>
      )}
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={() => setRecycling(true)}
        disabled={recycleItem.isPending}
      >
        <Recycle className="mr-1.5 h-3.5 w-3.5" />
        Recycle
      </Button>
      {recycleItem.isError && !blockedMessage && (
        <p className="text-sm text-destructive">{(recycleItem.error as Error).message}</p>
      )}

      <AlertDialog open={removing !== null} onOpenChange={(open) => !open && setRemoving(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Remove the {removing?.label} accent?</AlertDialogTitle>
            <AlertDialogDescription>
              The crafter&apos;s work is undone for good; there is no refund, and adding it back
              means another commission.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleConfirmRemove}
              className={cn(buttonVariants({ variant: 'destructive' }))}
            >
              Remove accent
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={recycling} onOpenChange={setRecycling}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Recycle {item.display_name}?</AlertDialogTitle>
            <AlertDialogDescription>
              The piece is destroyed permanently. You recover a fraction of its materials; never the
              work itself.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleConfirmRecycle}
              className={cn(buttonVariants({ variant: 'destructive' }))}
            >
              Recycle it
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog
        open={blockedMessage !== null}
        onOpenChange={(open) => !open && setBlockedMessage(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>A story stands in the way</AlertDialogTitle>
            <AlertDialogDescription>{blockedMessage}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Keep the piece</AlertDialogCancel>
            <AlertDialogAction onClick={handleRequestSignoff}>
              Request GM sign-off
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

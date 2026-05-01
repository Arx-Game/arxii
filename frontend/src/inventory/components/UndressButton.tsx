/**
 * UndressButton — small isolated control for stripping all worn items.
 *
 * UX rules:
 *   - Hidden entirely when nothing is equipped (no point in offering it).
 *   - With 1–2 items worn, fires immediately on click. Removing one or two
 *     pieces is cheap and reversible; an extra confirmation step would feel
 *     like a chore.
 *   - With 3+ items worn, opens a confirmation dialog. The action is
 *     coarse-grained at that point (whole loadout) and the player likely
 *     wants to know what they're about to undo.
 *
 * The button is presentation-only — it never invokes the undress service
 * itself; the parent passes `onUndress` and decides whether to dispatch a
 * websocket action, a REST mutation, etc.
 */

import { useState } from 'react';
import { Shirt } from 'lucide-react';
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
import { Button } from '@/components/ui/button';
import { buttonVariants } from '@/components/ui/button';
import { cn } from '@/lib/utils';

const CONFIRM_THRESHOLD = 3;

interface UndressButtonProps {
  /** Number of items currently equipped on the character. */
  equippedCount: number;
  /** Fired when the player confirms (or skips confirmation for small loadouts). */
  onUndress: () => void;
  /** Disable the button (e.g. while a previous action is in flight). */
  disabled?: boolean;
  className?: string;
}

export function UndressButton({
  equippedCount,
  onUndress,
  disabled,
  className,
}: UndressButtonProps) {
  const [confirming, setConfirming] = useState(false);

  if (equippedCount === 0) {
    return null;
  }

  function handleClick() {
    if (equippedCount >= CONFIRM_THRESHOLD) {
      setConfirming(true);
    } else {
      onUndress();
    }
  }

  function handleConfirm() {
    setConfirming(false);
    onUndress();
  }

  return (
    <>
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={handleClick}
        disabled={disabled}
        className={className}
      >
        <Shirt className="mr-1.5 h-3.5 w-3.5" />
        Undress
      </Button>
      <AlertDialog open={confirming} onOpenChange={setConfirming}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Remove all items?</AlertDialogTitle>
            <AlertDialogDescription>
              You&apos;re wearing {equippedCount} items. Removing them all will leave you in your
              skin. The pieces go back to your inventory — nothing is destroyed.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleConfirm}
              className={cn(buttonVariants({ variant: 'destructive' }))}
            >
              Remove all
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}

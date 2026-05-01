/**
 * DeleteOutfitDialog — destructive AlertDialog confirming outfit deletion.
 *
 * Deleting an outfit removes the saved arrangement + its slot rows. The item
 * instances themselves are not affected — they remain in the wardrobe / on
 * the character.
 */

import { toast } from 'sonner';
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
import { buttonVariants } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { useDeleteOutfit } from '../hooks/useOutfits';
import type { Outfit } from '../types';

interface DeleteOutfitDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  outfit: Outfit;
}

export function DeleteOutfitDialog({ open, onOpenChange, outfit }: DeleteOutfitDialogProps) {
  const deleteMutation = useDeleteOutfit();

  function handleConfirm(e: React.MouseEvent) {
    // Prevent AlertDialogAction's default close-on-click so we can keep the
    // dialog open if the mutation fails.
    e.preventDefault();
    deleteMutation.mutate(
      { id: outfit.id, characterSheetId: outfit.character_sheet },
      {
        onSuccess: () => {
          toast.success('Outfit deleted.');
          onOpenChange(false);
        },
        onError: (err) => {
          const message = err instanceof Error ? err.message : "Couldn't delete outfit.";
          toast.error(message);
        },
      }
    );
  }

  function handleOpenChange(next: boolean) {
    if (deleteMutation.isPending) return;
    onOpenChange(next);
  }

  return (
    <AlertDialog open={open} onOpenChange={handleOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Delete this outfit?</AlertDialogTitle>
          <AlertDialogDescription>
            Delete the outfit &ldquo;
            <span className="font-medium text-foreground">{outfit.name}</span>&rdquo;? The items
            themselves won&apos;t be affected — just the saved arrangement.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={deleteMutation.isPending}>Cancel</AlertDialogCancel>
          <AlertDialogAction
            className={cn(buttonVariants({ variant: 'destructive' }))}
            onClick={handleConfirm}
            disabled={deleteMutation.isPending}
          >
            {deleteMutation.isPending ? 'Deleting…' : 'Delete'}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

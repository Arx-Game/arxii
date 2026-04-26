/**
 * ExpireBeatsButton — staff-only action button that sweeps overdue beats.
 *
 * Click → AlertDialog confirm → useExpireOverdueBeats mutation → toast result.
 * This is idempotent and safe to run repeatedly.
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
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog';
import { Button } from '@/components/ui/button';
import { useExpireOverdueBeats } from '../queries';

export function ExpireBeatsButton() {
  const mutation = useExpireOverdueBeats();

  function handleConfirm() {
    mutation.mutate(undefined, {
      onSuccess: (data) => {
        toast.success(
          `Expired ${data.expired_count} overdue beat${data.expired_count === 1 ? '' : 's'}`
        );
      },
      onError: () => {
        toast.error('Failed to expire overdue beats. Please try again.');
      },
    });
  }

  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <Button variant="outline" disabled={mutation.isPending} data-testid="expire-beats-trigger">
          {mutation.isPending ? 'Expiring…' : 'Expire Overdue Beats'}
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Sweep overdue beats?</AlertDialogTitle>
          <AlertDialogDescription>
            Beats with past deadlines will be marked EXPIRED. This is idempotent and safe to run
            repeatedly.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction onClick={handleConfirm} data-testid="expire-beats-confirm">
            Expire Beats
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

/**
 * RevokeClearanceButton — soft-revoke a GRANTED CustodyClearance (#2001 Task 8).
 * Custodian GM or staff only; the caller decides whether to render this
 * button at all (ClearanceInbox hides rather than probes — see its docstring).
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
import { useRevokeClearance } from '../queries';

interface Props {
  clearanceId: number;
}

export function RevokeClearanceButton({ clearanceId }: Props) {
  const mutation = useRevokeClearance();

  function handleConfirm() {
    mutation.mutate(clearanceId, {
      onSuccess: () => toast.success('Clearance revoked'),
      onError: (err: unknown) => {
        if (err && typeof err === 'object' && 'response' in err) {
          const response = (err as { response?: Response }).response;
          if (response) {
            void response
              .json()
              .then((data: { detail?: string }) =>
                toast.error(data.detail ?? 'Failed to revoke clearance.')
              )
              .catch(() => toast.error('Failed to revoke clearance.'));
            return;
          }
        }
        toast.error('Failed to revoke clearance.');
      },
    });
  }

  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <Button
          variant="outline"
          size="sm"
          className="text-destructive hover:text-destructive"
          disabled={mutation.isPending}
          data-testid="revoke-clearance-btn"
        >
          {mutation.isPending ? 'Revoking…' : 'Revoke'}
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Revoke this clearance?</AlertDialogTitle>
          <AlertDialogDescription>
            The requesting GM will lose permission to act on this subject. This is a soft revoke —
            the decision trail is kept.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction onClick={handleConfirm}>Revoke</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

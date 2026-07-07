/**
 * EscalateClearanceButton — requester escalates their own DENIED or stale
 * PENDING CustodyClearance to staff (#2001 Task 8). No input needed — the
 * service takes no actor/reason parameter by design (Task 3 brief); confirm
 * only, mirroring ExpireBeatsButton's AlertDialog-confirm shape.
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
import { useEscalateClearance } from '../queries';

interface Props {
  clearanceId: number;
}

export function EscalateClearanceButton({ clearanceId }: Props) {
  const mutation = useEscalateClearance();

  function handleConfirm() {
    mutation.mutate(clearanceId, {
      onSuccess: () => toast.success('Escalated to staff'),
      onError: (err: unknown) => {
        if (err && typeof err === 'object' && 'response' in err) {
          const response = (err as { response?: Response }).response;
          if (response) {
            void response
              .json()
              .then((data: { detail?: string }) =>
                toast.error(data.detail ?? 'Failed to escalate clearance.')
              )
              .catch(() => toast.error('Failed to escalate clearance.'));
            return;
          }
        }
        toast.error('Failed to escalate clearance.');
      },
    });
  }

  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <Button
          variant="outline"
          size="sm"
          disabled={mutation.isPending}
          data-testid="escalate-clearance-btn"
        >
          {mutation.isPending ? 'Escalating…' : 'Escalate to staff'}
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Escalate to staff?</AlertDialogTitle>
          <AlertDialogDescription>
            Staff will make the final call on this clearance request.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction onClick={handleConfirm}>Escalate</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

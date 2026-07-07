/**
 * EscalateClearanceButton — requester escalates their own DENIED or stale
 * PENDING CustodyClearance to staff (#2001 Task 8). No input needed — the
 * service takes no actor/reason parameter by design (Task 3 brief); confirm
 * only, mirroring ExpireBeatsButton's AlertDialog-confirm shape.
 */

import { toast } from 'sonner';
import { useEscalateClearance } from '../queries';
import { ClearanceConfirmButton, makeClearanceToastHandler } from './clearanceShared';

interface Props {
  clearanceId: number;
}

export function EscalateClearanceButton({ clearanceId }: Props) {
  const mutation = useEscalateClearance();

  function handleConfirm() {
    mutation.mutate(clearanceId, {
      onSuccess: () => toast.success('Escalated to staff'),
      onError: makeClearanceToastHandler('Failed to escalate clearance.'),
    });
  }

  return (
    <ClearanceConfirmButton
      title="Escalate to staff?"
      description="Staff will make the final call on this clearance request."
      confirmLabel="Escalate"
      isPending={mutation.isPending}
      onConfirm={handleConfirm}
      triggerTestId="escalate-clearance-btn"
      triggerLabel="Escalate to staff"
      pendingLabel="Escalating…"
    />
  );
}

/**
 * RevokeClearanceButton — soft-revoke a GRANTED CustodyClearance (#2001 Task 8).
 * Custodian GM or staff only; the caller decides whether to render this
 * button at all (ClearanceInbox hides rather than probes — see its docstring).
 */

import { toast } from 'sonner';
import { useRevokeClearance } from '../queries';
import { ClearanceConfirmButton, makeClearanceToastHandler } from './clearanceShared';

interface Props {
  clearanceId: number;
}

export function RevokeClearanceButton({ clearanceId }: Props) {
  const mutation = useRevokeClearance();

  function handleConfirm() {
    mutation.mutate(clearanceId, {
      onSuccess: () => toast.success('Clearance revoked'),
      onError: makeClearanceToastHandler('Failed to revoke clearance.'),
    });
  }

  return (
    <ClearanceConfirmButton
      title="Revoke this clearance?"
      description="The requesting GM will lose permission to act on this subject. This is a soft revoke — the decision trail is kept."
      confirmLabel="Revoke"
      isPending={mutation.isPending}
      onConfirm={handleConfirm}
      triggerTestId="revoke-clearance-btn"
      triggerLabel="Revoke"
      pendingLabel="Revoking…"
      triggerClassName="text-destructive hover:text-destructive"
    />
  );
}

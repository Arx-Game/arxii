/**
 * GrantClearanceDialog — custodian GM grants a PENDING CustodyClearance
 * (#2001 Task 8). Mirrors ApproveClaimDialog's optional-note shape.
 */

import { toast } from 'sonner';
import { useGrantClearance } from '../queries';
import { ClearanceNoteDialog, handleInlineError } from './clearanceShared';

interface Props {
  clearanceId: number;
}

export function GrantClearanceDialog({ clearanceId }: Props) {
  const grantMutation = useGrantClearance();

  return (
    <ClearanceNoteDialog
      title="Grant clearance"
      noteLabel="Note"
      placeholder="Context for the requester…"
      submitLabel="Grant"
      pendingLabel="Granting…"
      isPending={grantMutation.isPending}
      successToast="Clearance granted"
      errorFallback="Failed to grant clearance."
      triggerTestId="grant-clearance-btn"
      triggerLabel="Grant"
      onSubmit={(note, { setError, close }) => {
        grantMutation.mutate(
          { id: clearanceId, body: { response_note: note } },
          {
            onSuccess: () => {
              toast.success('Clearance granted');
              close();
            },
            onError: (err) => handleInlineError(err, setError, 'Failed to grant clearance.'),
          }
        );
      }}
    />
  );
}

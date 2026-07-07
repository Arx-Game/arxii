/**
 * DenyClearanceDialog — custodian GM denies a PENDING CustodyClearance
 * (#2001 Task 8). Mirrors RejectClaimDialog's optional-note shape.
 */

import { toast } from 'sonner';
import { useDenyClearance } from '../queries';
import { ClearanceNoteDialog, handleInlineError } from './clearanceShared';

interface Props {
  clearanceId: number;
}

export function DenyClearanceDialog({ clearanceId }: Props) {
  const denyMutation = useDenyClearance();

  return (
    <ClearanceNoteDialog
      title="Deny clearance"
      noteLabel="Note"
      placeholder="Reason for denial…"
      submitLabel="Deny"
      pendingLabel="Denying…"
      isPending={denyMutation.isPending}
      successToast="Clearance denied"
      errorFallback="Failed to deny clearance."
      submitVariant="destructive"
      triggerTestId="deny-clearance-btn"
      triggerLabel="Deny"
      triggerVariant="destructive"
      onSubmit={(note, { setError, close }) => {
        denyMutation.mutate(
          { id: clearanceId, body: { response_note: note } },
          {
            onSuccess: () => {
              toast.success('Clearance denied');
              close();
            },
            onError: (err) => handleInlineError(err, setError, 'Failed to deny clearance.'),
          }
        );
      }}
    />
  );
}

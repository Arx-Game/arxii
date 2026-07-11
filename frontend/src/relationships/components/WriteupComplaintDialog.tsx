/**
 * WriteupComplaintDialog (#2159) — small reason-entry dialog backing the
 * "Report" button beside Commend on a SHARED/PUBLIC relationship writeup in
 * `RelationshipsSection`'s Writeups subsection.
 *
 * POSTs `.../relationship-updates/complaint/` (`writeup_type`/`writeup_id`/
 * `reason`, mirroring `WriteupComplaintWriteSerializer`). Staff-triage only —
 * `WriteupComplaint` never appears in any player-facing serializer (see
 * `world/relationships/CLAUDE.md`), so this dialog's only feedback is
 * "filed"; there is no follow-up read surface for the complainant.
 */

import { useState } from 'react';
import { toast } from 'sonner';

import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { extractErrorMessage } from '@/lib/errors';
import { useFileWriteupComplaint } from '../queries';
import type { WriteupTypeEnum } from '../api';

export interface WriteupComplaintDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  writeupType: WriteupTypeEnum;
  writeupId: number;
  writeupTitle: string;
}

export function WriteupComplaintDialog({
  open,
  onOpenChange,
  writeupType,
  writeupId,
  writeupTitle,
}: WriteupComplaintDialogProps) {
  const [reason, setReason] = useState('');
  const [localError, setLocalError] = useState<string | null>(null);
  const fileComplaint = useFileWriteupComplaint();

  function handleOpenChange(next: boolean) {
    if (!next) {
      setReason('');
      setLocalError(null);
    }
    onOpenChange(next);
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLocalError(null);

    if (reason.trim() === '') {
      setLocalError('A reason is required.');
      return;
    }

    fileComplaint.mutate(
      { writeup_type: writeupType, writeup_id: writeupId, reason: reason.trim() },
      {
        onSuccess: () => {
          toast.success('Reported for staff review.');
          handleOpenChange(false);
        },
        onError: (err) => {
          toast.error(extractErrorMessage(err, 'Failed to file this complaint'));
        },
      }
    );
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Report: {writeupTitle}</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1">
            <Label htmlFor="complaint-reason">Reason</Label>
            <Textarea
              id="complaint-reason"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              rows={4}
            />
          </div>

          {localError && <p className="text-sm text-destructive">{localError}</p>}

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => handleOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={fileComplaint.isPending}>
              Submit report
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

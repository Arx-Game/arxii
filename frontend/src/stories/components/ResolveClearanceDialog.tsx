/**
 * ResolveClearanceDialog — staff tiebreak on an ESCALATED CustodyClearance
 * (#2001 Task 8). Body is `{grant: boolean, response_note}` — the only door
 * in for staff to decide an escalation (IsStaffForCustodyResolution).
 */

import { useState } from 'react';
import { toast } from 'sonner';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { useResolveClearance } from '../queries';

interface DRFFieldErrors {
  detail?: string;
  non_field_errors?: string[];
}

interface Props {
  clearanceId: number;
}

export function ResolveClearanceDialog({ clearanceId }: Props) {
  const [open, setOpen] = useState(false);
  const [note, setNote] = useState('');
  const [error, setError] = useState('');

  const resolveMutation = useResolveClearance();

  function handleOpenChange(next: boolean) {
    setOpen(next);
    if (!next) {
      setNote('');
      setError('');
    }
  }

  function handleResolve(grant: boolean) {
    setError('');
    resolveMutation.mutate(
      { id: clearanceId, body: { grant, response_note: note.trim() } },
      {
        onSuccess: () => {
          toast.success(grant ? 'Escalation resolved: granted' : 'Escalation resolved: denied');
          handleOpenChange(false);
        },
        onError: (err: unknown) => {
          if (err && typeof err === 'object' && 'response' in err) {
            const response = (err as { response?: Response }).response;
            if (response) {
              void response
                .json()
                .then((data: unknown) => {
                  const drf = data as DRFFieldErrors;
                  setError(drf.detail ?? drf.non_field_errors?.join(' ') ?? 'Failed to resolve.');
                })
                .catch(() => setError('Failed to resolve escalation.'));
              return;
            }
          }
          setError(err instanceof Error ? err.message : 'Failed to resolve escalation.');
        },
      }
    );
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger asChild>
        <Button size="sm" data-testid="resolve-clearance-btn">
          Resolve
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Resolve escalated clearance</DialogTitle>
        </DialogHeader>
        <div className="mt-4 space-y-1.5">
          <Label htmlFor="resolve-note">
            Note <span className="text-muted-foreground">(optional)</span>
          </Label>
          <Textarea
            id="resolve-note"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            rows={3}
            placeholder="Rationale for the tiebreak…"
          />
        </div>
        {error && <p className="mt-2 text-sm text-destructive">{error}</p>}
        <DialogFooter className="mt-4">
          <Button
            type="button"
            variant="outline"
            onClick={() => handleOpenChange(false)}
            disabled={resolveMutation.isPending}
          >
            Cancel
          </Button>
          <Button
            type="button"
            variant="destructive"
            onClick={() => handleResolve(false)}
            disabled={resolveMutation.isPending}
            data-testid="resolve-clearance-deny-btn"
          >
            Deny
          </Button>
          <Button
            type="button"
            onClick={() => handleResolve(true)}
            disabled={resolveMutation.isPending}
            data-testid="resolve-clearance-grant-btn"
          >
            Grant
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

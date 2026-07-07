/**
 * DenyClearanceDialog — custodian GM denies a PENDING CustodyClearance
 * (#2001 Task 8). Mirrors RejectClaimDialog's optional-note shape.
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
import { useDenyClearance } from '../queries';

interface DRFFieldErrors {
  detail?: string;
  non_field_errors?: string[];
}

interface Props {
  clearanceId: number;
}

export function DenyClearanceDialog({ clearanceId }: Props) {
  const [open, setOpen] = useState(false);
  const [note, setNote] = useState('');
  const [error, setError] = useState('');

  const denyMutation = useDenyClearance();

  function handleOpenChange(next: boolean) {
    setOpen(next);
    if (!next) {
      setNote('');
      setError('');
    }
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    denyMutation.mutate(
      { id: clearanceId, body: { response_note: note.trim() } },
      {
        onSuccess: () => {
          toast.success('Clearance denied');
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
                  setError(drf.detail ?? drf.non_field_errors?.join(' ') ?? 'Failed to deny.');
                })
                .catch(() => setError('Failed to deny clearance.'));
              return;
            }
          }
          setError(err instanceof Error ? err.message : 'Failed to deny clearance.');
        },
      }
    );
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger asChild>
        <Button variant="destructive" size="sm" data-testid="deny-clearance-btn">
          Deny
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>Deny clearance</DialogTitle>
          </DialogHeader>
          <div className="mt-4 space-y-1.5">
            <Label htmlFor="deny-note">
              Note <span className="text-muted-foreground">(optional)</span>
            </Label>
            <Textarea
              id="deny-note"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              rows={3}
              placeholder="Reason for denial…"
            />
          </div>
          {error && <p className="mt-2 text-sm text-destructive">{error}</p>}
          <DialogFooter className="mt-4">
            <Button
              type="button"
              variant="outline"
              onClick={() => handleOpenChange(false)}
              disabled={denyMutation.isPending}
            >
              Cancel
            </Button>
            <Button type="submit" variant="destructive" disabled={denyMutation.isPending}>
              {denyMutation.isPending ? 'Denying…' : 'Deny'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

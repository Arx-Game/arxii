/**
 * GrantClearanceDialog — custodian GM grants a PENDING CustodyClearance
 * (#2001 Task 8). Mirrors ApproveClaimDialog's optional-note shape.
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
import { useGrantClearance } from '../queries';

interface DRFFieldErrors {
  detail?: string;
  non_field_errors?: string[];
}

interface Props {
  clearanceId: number;
}

export function GrantClearanceDialog({ clearanceId }: Props) {
  const [open, setOpen] = useState(false);
  const [note, setNote] = useState('');
  const [error, setError] = useState('');

  const grantMutation = useGrantClearance();

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
    grantMutation.mutate(
      { id: clearanceId, body: { response_note: note.trim() } },
      {
        onSuccess: () => {
          toast.success('Clearance granted');
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
                  setError(drf.detail ?? drf.non_field_errors?.join(' ') ?? 'Failed to grant.');
                })
                .catch(() => setError('Failed to grant clearance.'));
              return;
            }
          }
          setError(err instanceof Error ? err.message : 'Failed to grant clearance.');
        },
      }
    );
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger asChild>
        <Button size="sm" data-testid="grant-clearance-btn">
          Grant
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>Grant clearance</DialogTitle>
          </DialogHeader>
          <div className="mt-4 space-y-1.5">
            <Label htmlFor="grant-note">
              Note <span className="text-muted-foreground">(optional)</span>
            </Label>
            <Textarea
              id="grant-note"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              rows={3}
              placeholder="Context for the requester…"
            />
          </div>
          {error && <p className="mt-2 text-sm text-destructive">{error}</p>}
          <DialogFooter className="mt-4">
            <Button
              type="button"
              variant="outline"
              onClick={() => handleOpenChange(false)}
              disabled={grantMutation.isPending}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={grantMutation.isPending}>
              {grantMutation.isPending ? 'Granting…' : 'Grant'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

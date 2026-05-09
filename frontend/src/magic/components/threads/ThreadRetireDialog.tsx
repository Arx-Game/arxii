/**
 * ThreadRetireDialog — hard-confirm before retiring a thread.
 *
 * On confirm, calls useRetireThread then navigates back to /threads.
 */
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { useRetireThread } from '../../queries';
import type { Thread } from '../../types';

interface ThreadRetireDialogProps {
  thread: Thread;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function ThreadRetireDialog({ thread, open, onOpenChange }: ThreadRetireDialogProps) {
  const navigate = useNavigate();
  const { mutate, isPending, error, isError } = useRetireThread();

  const handleConfirm = () => {
    mutate(thread.id, {
      onSuccess: () => {
        onOpenChange(false);
        void navigate('/threads');
      },
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="thread-retire-dialog">
        <DialogHeader>
          <DialogTitle>Retire Thread?</DialogTitle>
          <DialogDescription data-testid="thread-retire-description">
            Retired threads stop pulling and never grant passive effects. They remain in your
            history. This cannot be undone.
          </DialogDescription>
        </DialogHeader>

        {isError && (
          <p className="text-sm text-destructive" role="alert" data-testid="thread-retire-error">
            {error instanceof Error ? error.message : 'Failed to retire thread.'}
          </p>
        )}

        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={isPending}
          >
            Cancel
          </Button>
          <Button
            type="button"
            variant="destructive"
            onClick={handleConfirm}
            disabled={isPending}
            data-testid="thread-retire-confirm"
          >
            {isPending ? 'Retiring…' : 'Retire Thread'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

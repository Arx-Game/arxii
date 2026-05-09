/**
 * ThreadRenameDialog — form to rename a thread (name + description).
 * Submits via usePatchThreadNarrative. Closes on success.
 */
import { useState } from 'react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { usePatchThreadNarrative } from '../../queries';
import type { Thread } from '../../types';

interface ThreadRenameDialogProps {
  thread: Thread;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function ThreadRenameDialog({ thread, open, onOpenChange }: ThreadRenameDialogProps) {
  const [name, setName] = useState(thread.name);
  const [description, setDescription] = useState(thread.description);

  const { mutate, isPending, error, isError } = usePatchThreadNarrative(thread.id);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    mutate(
      { name, description },
      {
        onSuccess: () => {
          onOpenChange(false);
        },
      }
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="thread-rename-dialog">
        <DialogHeader>
          <DialogTitle>Edit Thread</DialogTitle>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="thread-name">Name</Label>
            <Input
              id="thread-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              maxLength={120}
              placeholder="(unnamed)"
              data-testid="thread-rename-name"
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="thread-description">Description</Label>
            <Textarea
              id="thread-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Optional description…"
              rows={4}
              data-testid="thread-rename-description"
            />
          </div>

          {isError && (
            <p className="text-sm text-destructive" role="alert" data-testid="thread-rename-error">
              {error instanceof Error ? error.message : 'Failed to update thread.'}
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
            <Button type="submit" disabled={isPending} data-testid="thread-rename-submit">
              {isPending ? 'Saving…' : 'Save'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

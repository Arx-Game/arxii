/**
 * Small dialog that adds a node to a mission. The server's validation
 * message (duplicate key, bad characters) is shown inline under the field.
 * The first node of a mission becomes its entry node.
 */

import { useEffect, useState } from 'react';

import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  NO_DESCRIPTION,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

import { useCreateMissionNode } from '../queries';

interface AddNodeDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  templateId: number;
  /** True when the mission has no nodes yet, so the new one is its entry. */
  isFirstNode: boolean;
}

export function AddNodeDialog({ open, onOpenChange, templateId, isFirstNode }: AddNodeDialogProps) {
  const [key, setKey] = useState('');
  const [error, setError] = useState<string | null>(null);
  const create = useCreateMissionNode();

  useEffect(() => {
    if (open) {
      setKey('');
      setError(null);
    }
  }, [open]);

  const onSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    const trimmed = key.trim();
    if (!trimmed) {
      setError('Give the node a key.');
      return;
    }
    try {
      // The server requires a conflict mode; group vote is the usual one and the node page changes it.
      await create.mutateAsync({
        template: templateId,
        key: trimmed,
        is_entry: isFirstNode,
        conflict_mode: 'group_vote',
      });
      onOpenChange(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to add node');
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent {...(isFirstNode ? {} : NO_DESCRIPTION)}>
        <form onSubmit={onSubmit} className="space-y-4">
          <DialogHeader>
            <DialogTitle>Add node</DialogTitle>
            {isFirstNode ? (
              <DialogDescription>
                This is the first node, so it becomes the entry node.
              </DialogDescription>
            ) : null}
          </DialogHeader>
          <div className="space-y-1">
            <Label htmlFor="add-node-key">Node key</Label>
            <Input
              id="add-node-key"
              value={key}
              onChange={(e) => setKey(e.target.value)}
              aria-invalid={error !== null}
              autoFocus
            />
            {error && (
              <p role="alert" className="text-sm text-destructive">
                {error}
              </p>
            )}
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={create.isPending}>
              Add node
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

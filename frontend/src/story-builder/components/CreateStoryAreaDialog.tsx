/**
 * CreateStoryAreaDialog — new GM story area (#2450).
 *
 * Story areas are always created flat (`level=AreaLevel.BUILDING`, no
 * parent — see `world.gm.story_services.create_story_area`), so unlike
 * world-builder's `CreateAreaDialog` this has no slug/level/parent fields:
 * just name + description, matching `CreateStoryAreaAction`'s exact kwargs.
 */
import { useEffect, useState } from 'react';

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

export interface CreateStoryAreaDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  runAction: (key: string, kwargs: Record<string, unknown>) => void;
}

export function CreateStoryAreaDialog({
  open,
  onOpenChange,
  runAction,
}: CreateStoryAreaDialogProps) {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');

  useEffect(() => {
    if (open) {
      setName('');
      setDescription('');
    }
  }, [open]);

  const canSubmit = name.trim() !== '';

  const submit = () => {
    const kwargs: Record<string, unknown> = { name: name.trim() };
    if (description.trim()) kwargs.description = description.trim();
    runAction('create_story_area', kwargs);
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>New story area</DialogTitle>
        </DialogHeader>
        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="create-story-area-name">Name</Label>
            <Input
              id="create-story-area-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="create-story-area-description">Description (optional)</Label>
            <Textarea
              id="create-story-area-description"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              rows={3}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={!canSubmit} data-testid="create-story-area-submit">
            Create
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

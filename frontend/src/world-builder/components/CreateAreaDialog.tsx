/**
 * CreateAreaDialog — new AUTHORED area, optionally nested under a parent
 * (#2449). Reached from the area tree's "+" affordances (root or per-node).
 * Editing an existing area's name/slug/level/parent (`edit_area`) is a
 * deferred follow-up — out of scope for this slice (see task-6 report).
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

import { AREA_LEVELS } from '../types';
import type { WorldBuilderActionKey } from '../types';

export interface CreateAreaDialogProps {
  /** null creates a root area. */
  parentId: number | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  runAction: (key: WorldBuilderActionKey, kwargs: Record<string, unknown>) => void;
}

export function CreateAreaDialog({
  parentId,
  open,
  onOpenChange,
  runAction,
}: CreateAreaDialogProps) {
  const [name, setName] = useState('');
  const [slug, setSlug] = useState('');
  const [level, setLevel] = useState('');

  useEffect(() => {
    if (open) {
      setName('');
      setSlug('');
      setLevel('');
    }
  }, [open]);

  const canSubmit = name.trim() !== '' && slug.trim() !== '' && level !== '';

  const submit = () => {
    const kwargs: Record<string, unknown> = {
      name: name.trim(),
      slug: slug.trim(),
      level: Number(level),
    };
    if (parentId != null) kwargs.parent_id = parentId;
    runAction('create_area', kwargs);
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{parentId != null ? 'New sub-area' : 'New root area'}</DialogTitle>
        </DialogHeader>
        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="create-area-name">Name</Label>
            <Input
              id="create-area-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="create-area-slug">Slug</Label>
            <Input
              id="create-area-slug"
              value={slug}
              onChange={(event) => setSlug(event.target.value)}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="create-area-level">Level</Label>
            <Select value={level} onValueChange={setLevel}>
              <SelectTrigger id="create-area-level">
                <SelectValue placeholder="Pick a level" />
              </SelectTrigger>
              <SelectContent>
                {AREA_LEVELS.map((choice) => (
                  <SelectItem key={choice.value} value={String(choice.value)}>
                    {choice.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={!canSubmit} data-testid="create-area-submit">
            Create
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

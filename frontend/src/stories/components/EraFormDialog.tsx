/**
 * EraFormDialog — create / edit an era.
 *
 * Create mode: all fields editable; status forced to UPCOMING (lifecycle
 * transitions go through advance/archive, not direct edits).
 *
 * Edit mode: name, display_name, season_number, description are editable;
 * status is read-only to prevent bypassing the lifecycle service's atomic
 * guarantees.
 */

import { useEffect, useState } from 'react';
import { toast } from 'sonner';
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
import { useCreateEra, useUpdateEra } from '../queries';
import { EraStatusBadge } from './EraStatusBadge';
import type { Era, EraCreateBody } from '../types';

interface EraFormDialogProps {
  open: boolean;
  onClose: () => void;
  era?: Era | null;
}

function emptyForm(): EraCreateBody {
  return { name: '', display_name: '', season_number: 1, description: '', status: 'upcoming' };
}

export function EraFormDialog({ open, onClose, era }: EraFormDialogProps) {
  const isEdit = era != null;
  const [form, setForm] = useState<EraCreateBody>(emptyForm);
  const createEra = useCreateEra();
  const updateEra = useUpdateEra();

  useEffect(() => {
    if (open) {
      if (era) {
        setForm({
          name: era.name,
          display_name: era.display_name,
          season_number: era.season_number,
          description: era.description,
          status: era.status,
        });
      } else {
        setForm(emptyForm());
      }
    }
  }, [open, era]);

  function handleChange(field: keyof EraCreateBody, value: string | number) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    try {
      if (isEdit && era) {
        await updateEra.mutateAsync({
          id: era.id,
          data: {
            name: form.name,
            display_name: form.display_name,
            season_number: form.season_number,
            description: form.description,
          },
        });
        toast.success(`Era "${form.display_name}" updated.`);
      } else {
        await createEra.mutateAsync({ ...form, status: 'upcoming' });
        toast.success(`Era "${form.display_name}" created.`);
      }
      onClose();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to save era.');
    }
  }

  const isPending = createEra.isPending || updateEra.isPending;

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{isEdit ? 'Edit Era' : 'Create Era'}</DialogTitle>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Status — read-only in edit mode */}
          {isEdit && era && (
            <div className="flex items-center gap-2">
              <Label>Status</Label>
              <EraStatusBadge status={era.status} />
              <span className="text-xs text-muted-foreground">
                (Use Advance or Archive to change status)
              </span>
            </div>
          )}

          <div className="space-y-1">
            <Label htmlFor="era-name">Slug name</Label>
            <Input
              id="era-name"
              value={form.name}
              onChange={(e) => handleChange('name', e.target.value)}
              placeholder="age_of_embers"
              required
              pattern="[a-z0-9_-]+"
              title="Lowercase letters, numbers, hyphens, underscores only"
            />
          </div>

          <div className="space-y-1">
            <Label htmlFor="era-display-name">Display name</Label>
            <Input
              id="era-display-name"
              value={form.display_name}
              onChange={(e) => handleChange('display_name', e.target.value)}
              placeholder="Age of Embers"
              required
            />
          </div>

          <div className="space-y-1">
            <Label htmlFor="era-season">Season number</Label>
            <Input
              id="era-season"
              type="number"
              min={1}
              value={form.season_number}
              onChange={(e) => handleChange('season_number', parseInt(e.target.value, 10))}
              required
            />
          </div>

          <div className="space-y-1">
            <Label htmlFor="era-description">Description</Label>
            <Textarea
              id="era-description"
              value={form.description}
              onChange={(e) => handleChange('description', e.target.value)}
              rows={4}
              placeholder="Summary of this era's themes and events…"
            />
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose} disabled={isPending}>
              Cancel
            </Button>
            <Button type="submit" disabled={isPending}>
              {isPending ? 'Saving…' : isEdit ? 'Save changes' : 'Create'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

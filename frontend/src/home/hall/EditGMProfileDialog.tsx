/**
 * EditGMProfileDialog — edit the account's own GM operational info (#3478
 * task 5): `contact_times` and `ooc_info`, the only writable fields on
 * `GET/PATCH /api/gm/profiles/mine/` (`level`/`level_display` are read-only
 * — Task 1). Portrait/description are NOT here — the GM card links to the
 * character's normal profile page like any character card does.
 *
 * Reached only from `GMSlot`'s edit affordance, which itself only renders
 * once `mine` has resolved successfully (never on a 404) — so this dialog
 * can assume a profile exists once opened, and reuses the same
 * `useGMProfileMineQuery` cache entry `GMSlot` already populated.
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
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { useGMProfileMineQuery, useUpdateGMProfileMineMutation } from './queries';

export interface EditGMProfileDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function EditGMProfileDialog({ open, onOpenChange }: EditGMProfileDialogProps) {
  const mineQuery = useGMProfileMineQuery(open);
  const saveMutation = useUpdateGMProfileMineMutation();
  const [contactTimes, setContactTimes] = useState('');
  const [oocInfo, setOocInfo] = useState('');

  useEffect(() => {
    if (open && mineQuery.data) {
      setContactTimes(mineQuery.data.contact_times ?? '');
      setOocInfo(mineQuery.data.ooc_info ?? '');
    }
  }, [open, mineQuery.data]);

  const submit = () => {
    saveMutation.mutate(
      { contact_times: contactTimes, ooc_info: oocInfo },
      { onSuccess: () => onOpenChange(false) }
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Edit GM Profile</DialogTitle>
        </DialogHeader>
        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="gm-contact-times">Contact times</Label>
            <Textarea
              id="gm-contact-times"
              value={contactTimes}
              onChange={(event) => setContactTimes(event.target.value)}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="gm-ooc-info">OOC info</Label>
            <Textarea
              id="gm-ooc-info"
              value={oocInfo}
              onChange={(event) => setOocInfo(event.target.value)}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={submit}
            disabled={saveMutation.isPending}
            data-testid="edit-gm-profile-save"
          >
            Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

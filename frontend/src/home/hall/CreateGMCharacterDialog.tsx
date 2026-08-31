/**
 * CreateGMCharacterDialog — mints the account's own GM/Staff character from
 * the Hall's GM slot (#3478 task 5). One name field; role gating (staff vs.
 * approved GM vs. refused) is entirely server-side
 * (`mint_gm_character`/`useMintGMCharacterMutation`) — this dialog only
 * surfaces whatever message the mutation's `onError` produces.
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
import { useMintGMCharacterMutation } from './queries';

export interface CreateGMCharacterDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function CreateGMCharacterDialog({ open, onOpenChange }: CreateGMCharacterDialogProps) {
  const [name, setName] = useState('');
  const mintMutation = useMintGMCharacterMutation();

  useEffect(() => {
    if (open) setName('');
  }, [open]);

  const canSubmit = name.trim() !== '' && !mintMutation.isPending;

  const submit = () => {
    mintMutation.mutate(name.trim(), { onSuccess: () => onOpenChange(false) });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Create GM Profile</DialogTitle>
        </DialogHeader>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="gm-character-name">Name</Label>
          <Input
            id="gm-character-name"
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={!canSubmit} data-testid="create-gm-character-submit">
            Create
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

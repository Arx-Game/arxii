/**
 * PlacePortalAnchorDialog — install a PortalAnchor in the selected room (#2451).
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

export interface PlacePortalAnchorDialogProps {
  roomId: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Keyed generically (not `WorldBuilderActionKey`) to match the story palette's own union (#2450). */
  runAction: (key: string, kwargs: Record<string, unknown>) => void;
}

export function PlacePortalAnchorDialog({
  roomId,
  open,
  onOpenChange,
  runAction,
}: PlacePortalAnchorDialogProps) {
  const [kindName, setKindName] = useState('');
  const [name, setName] = useState('');

  useEffect(() => {
    if (open) {
      setKindName('');
      setName('');
    }
  }, [open]);

  const canSubmit = kindName.trim() !== '' && name.trim() !== '';

  const submit = () => {
    runAction('staff_place_portal_anchor', {
      room_id: roomId,
      kind_name: kindName.trim(),
      name: name.trim(),
    });
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Place portal anchor</DialogTitle>
        </DialogHeader>
        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="place-anchor-kind">Anchor kind</Label>
            <Input
              id="place-anchor-kind"
              value={kindName}
              onChange={(event) => setKindName(event.target.value)}
              placeholder="Mirror"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="place-anchor-name">Anchor name</Label>
            <Input
              id="place-anchor-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="a tall silvered mirror"
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={!canSubmit} data-testid="place-portal-anchor-submit">
            Install
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

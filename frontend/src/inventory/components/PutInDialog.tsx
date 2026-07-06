/**
 * PutInDialog — modal opened from ItemDetailPanel's Put In button (#1909).
 *
 * The `put_in` action needs a `container` (another carried item, resolved
 * via the websocket dispatcher's `container_id` kwarg). Fed by the
 * character's own container-capable inventory items — a minimal select,
 * not a reusable target-picker framework.
 */

import { useEffect, useState } from 'react';
import { Package } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import type { ItemInstance } from '../types';

interface PutInDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Carried items with `template.is_container` true (the item itself already excluded). */
  containers: ItemInstance[];
  onConfirm: (containerId: number) => void;
}

export function PutInDialog({ open, onOpenChange, containers, onConfirm }: PutInDialogProps) {
  const [containerId, setContainerId] = useState<string>(
    containers[0] ? String(containers[0].id) : ''
  );

  useEffect(() => {
    if (open) {
      setContainerId(containers[0] ? String(containers[0].id) : '');
    }
  }, [open, containers]);

  const hasNoContainers = containers.length === 0;

  function handleConfirm() {
    if (!containerId) return;
    onConfirm(Number(containerId));
    onOpenChange(false);
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>Put item in…</DialogTitle>
          <DialogDescription>Choose a container from your inventory.</DialogDescription>
        </DialogHeader>

        {hasNoContainers ? (
          <div className="flex flex-col items-center justify-center gap-3 px-4 py-8 text-center">
            <Package className="h-8 w-8 text-muted-foreground/50" aria-hidden="true" />
            <p className="text-sm text-muted-foreground">
              You aren&apos;t carrying any containers.
            </p>
          </div>
        ) : (
          <Select value={containerId} onValueChange={setContainerId}>
            <SelectTrigger>
              <SelectValue placeholder="Choose a container…" />
            </SelectTrigger>
            <SelectContent>
              {containers.map((container) => (
                <SelectItem key={container.id} value={String(container.id)}>
                  {container.display_name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}

        <DialogFooter className="mt-2">
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button type="button" onClick={handleConfirm} disabled={hasNoContainers}>
            Put In
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

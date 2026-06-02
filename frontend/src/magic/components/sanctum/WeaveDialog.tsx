/**
 * WeaveDialog — bind a SANCTUM-target Thread (Plan 4 §F).
 *
 * Slot picker enforces the per-PC rules:
 * - PERSONAL_OWN: only valid on your own Personal Sanctum (one active per character)
 * - COVENANT: only valid on a Covenant Sanctum you're an active member of (one active)
 * - HELPER: valid on someone else's Personal Sanctum (unbounded)
 * The backend rejects mismatched slots with the typed `user_message` surface.
 */

import { useState } from 'react';

import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

import { useWeaveSanctumThread } from '../../sanctumQueries';
import type { SanctumDetails, SanctumSlotKind } from '../../sanctumTypes';

export interface WeaveDialogProps {
  sanctum: SanctumDetails;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

function extractErrorMessage(error: unknown): string {
  if (error instanceof Error && error.message) return error.message;
  return 'Failed to weave Sanctum thread';
}

const SLOT_LABELS: Record<SanctumSlotKind, string> = {
  PERSONAL_OWN: 'Personal — my own home',
  COVENANT: 'Covenant — my sworn ground',
  HELPER: 'Helper — invited ally',
};

export function WeaveDialog({ sanctum, open, onOpenChange }: WeaveDialogProps) {
  const [slotKind, setSlotKind] = useState<SanctumSlotKind>(
    sanctum.owner_mode === 'COVENANT' ? 'COVENANT' : 'PERSONAL_OWN'
  );
  const mutation = useWeaveSanctumThread(sanctum.feature_instance_id);

  function handleSubmit(): void {
    mutation.mutate({ slot_kind: slotKind }, { onSuccess: () => onOpenChange(false) });
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Weave thread into this Sanctum</DialogTitle>
          <DialogDescription>
            Bind yourself to this {sanctum.resonance_type_name} Sanctum. You'll receive a share of
            its passive resonance income on every tick.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="slot-kind">Slot</Label>
            <Select
              value={slotKind}
              onValueChange={(value) => setSlotKind(value as SanctumSlotKind)}
            >
              <SelectTrigger id="slot-kind">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {(Object.keys(SLOT_LABELS) as SanctumSlotKind[]).map((kind) => (
                  <SelectItem key={kind} value={kind}>
                    {SLOT_LABELS[kind]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          {mutation.isError ? (
            <p className="text-sm text-destructive">{extractErrorMessage(mutation.error)}</p>
          ) : null}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={mutation.isPending}>
            {mutation.isPending ? 'Weaving…' : 'Weave thread'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

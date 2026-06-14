import { useEffect, useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import type { ScenePersona } from '../types';

interface WhisperReceiverPickerProps {
  open: boolean;
  onClose: () => void;
  /** The action's target — always hears the whisper; shown as a fixed recipient. */
  targetName: string;
  /** Other present personas the player may add as listeners. */
  candidates: ScenePersona[];
  /** Called with the additional persona ids to whisper to (target is added by the caller). */
  onConfirm: (receiverIds: number[]) => void;
}

/**
 * #907 — choose extra listeners for a "Subtly" (whisper) action. The action
 * target always hears it; this picks additional scene participants who also do.
 */
export function WhisperReceiverPicker({
  open,
  onClose,
  targetName,
  candidates,
  onConfirm,
}: WhisperReceiverPickerProps) {
  const [selected, setSelected] = useState<Set<number>>(new Set());

  // Reset the selection whenever the dialog (re)opens.
  useEffect(() => {
    if (open) setSelected(new Set());
  }, [open]);

  function toggle(id: number) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  return (
    <Dialog open={open} onOpenChange={(isOpen) => !isOpen && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Whisper to…</DialogTitle>
          <DialogDescription>
            {targetName} hears this. Choose anyone else who should overhear it.
          </DialogDescription>
        </DialogHeader>

        {candidates.length === 0 ? (
          <p className="py-2 text-sm text-muted-foreground" data-testid="whisper-picker-empty">
            No one else is present to overhear.
          </p>
        ) : (
          <ul className="max-h-64 space-y-2 overflow-y-auto" data-testid="whisper-picker-list">
            {candidates.map((persona) => (
              <li key={persona.id}>
                <label className="flex cursor-pointer items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={selected.has(persona.id)}
                    onChange={() => toggle(persona.id)}
                    className="h-4 w-4 rounded border-input"
                  />
                  {persona.name}
                </label>
              </li>
            ))}
          </ul>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={() => onConfirm(Array.from(selected))}>
            {selected.size > 0 ? `Whisper to ${selected.size + 1}` : 'Whisper to target only'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

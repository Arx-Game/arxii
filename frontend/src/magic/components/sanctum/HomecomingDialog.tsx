/**
 * HomecomingDialog — Ritual of Homecoming form (Plan 4 §F).
 *
 * Sacrifice resonance to grow the Sanctum's reservoir. 100:1 efficiency
 * (the backend computes gain). Server-side cap (owner Path-level × 10
 * for Personal) routes overflow to escrow on `pending_sacrifice_overflow`.
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
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

import { useHomecoming } from '../../sanctumQueries';
import type { SanctumDetails } from '../../sanctumTypes';

export interface HomecomingDialogProps {
  sanctum: SanctumDetails;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

function extractErrorMessage(error: unknown): string {
  if (error instanceof Error && error.message) return error.message;
  return 'Failed to perform Ritual of Homecoming';
}

export function HomecomingDialog({ sanctum, open, onOpenChange }: Readonly<HomecomingDialogProps>) {
  const [sacrifice, setSacrifice] = useState<number>(100);
  const [narrative, setNarrative] = useState<string>('');
  const mutation = useHomecoming(sanctum.feature_instance_id);

  function handleSubmit(): void {
    mutation.mutate(
      { resonance_sacrificed: sacrifice, narrative_text: narrative },
      {
        onSuccess: () => {
          setSacrifice(100);
          setNarrative('');
          onOpenChange(false);
        },
      }
    );
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Ritual of Homecoming</DialogTitle>
          <DialogDescription>
            Consecrate this Sanctum by sacrificing {sanctum.resonance_type_name} resonance from your
            own reserves. 100 sacrificed becomes 1 imbued; any imbued past your cap is escrowed
            until your Path grows.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="sacrifice">Resonance to sacrifice</Label>
            <Input
              id="sacrifice"
              type="number"
              min={1}
              value={sacrifice}
              onChange={(e) => setSacrifice(Math.max(1, Number(e.target.value) || 1))}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="narrative">Narrative (optional)</Label>
            <textarea
              id="narrative"
              className="w-full rounded-md border border-input bg-background p-2 text-sm"
              rows={4}
              placeholder="What does this consecration look like?"
              value={narrative}
              onChange={(e) => setNarrative(e.target.value)}
              maxLength={4000}
            />
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
            {mutation.isPending ? 'Consecrating…' : 'Perform Ritual'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/**
 * SacrificeDialog (#4333, #4500) — give up items you carry at a being's shrine or temple. Each
 * item with meaning for you (carried, a gift, an heirloom, your own work, made by a tie) rolls a
 * check eased by that meaning; an item with none is given up for nothing. The price never counts.
 * The server answers with each item's calculation. Dispatches `sacrifice` as the character; the
 * server refuses it away from a holy site.
 */

import { useState } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { useInventory } from '@/inventory/hooks/useInventory';
import { useSacrifice } from '../queries';

interface SacrificeDialogProps {
  /** The acting character's sheet (= ObjectDB) pk. */
  characterId: number;
  /** The being the place is holy to, when the caller knows it (a shrine's card). */
  beingId?: number | null;
  beingName?: string | null;
  size?: 'sm' | 'default';
  variant?: 'default' | 'outline';
}

export function SacrificeDialog({
  characterId,
  beingId,
  beingName,
  size = 'sm',
  variant = 'outline',
}: SacrificeDialogProps) {
  const [open, setOpen] = useState(false);
  const [chosen, setChosen] = useState<number[]>([]);
  const [line, setLine] = useState('');
  const { data: items } = useInventory(open ? characterId : undefined);
  const mutation = useSacrifice(characterId);

  function toggle(id: number) {
    setChosen((current) =>
      current.includes(id) ? current.filter((row) => row !== id) : [...current, id]
    );
  }

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (chosen.length === 0) {
      toast.error('Choose what to sacrifice.');
      return;
    }
    mutation.mutate(
      { itemIds: chosen, being: beingId ?? null, playerLine: line.trim() },
      {
        onSuccess: (result) => {
          if (result.success === false) {
            toast.error(result.message);
            return;
          }
          toast.success(result.message);
          setChosen([]);
          setLine('');
          setOpen(false);
        },
        onError: (error: Error) => toast.error(error.message),
      }
    );
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant={variant} size={size} data-testid="sacrifice-button">
          Sacrifice
        </Button>
      </DialogTrigger>
      <DialogContent aria-describedby={undefined}>
        <form onSubmit={handleSubmit} className="space-y-4">
          <DialogHeader>
            <DialogTitle>Sacrifice{beingName ? ` to ${beingName}` : ''}</DialogTitle>
          </DialogHeader>
          {(items ?? []).length === 0 ? (
            <p className="text-sm text-muted-foreground">You carry nothing to give up.</p>
          ) : (
            <ul className="max-h-72 space-y-1 overflow-y-auto" data-testid="sacrifice-items">
              {(items ?? []).map((item) => (
                <li key={item.id}>
                  <label className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={chosen.includes(item.id)}
                      onChange={() => toggle(item.id)}
                    />
                    <span>{item.display_name}</span>
                  </label>
                </li>
              ))}
            </ul>
          )}
          <div className="space-y-1">
            <Label htmlFor="sacrifice-line">Your own line (optional)</Label>
            <Input
              id="sacrifice-line"
              value={line}
              maxLength={200}
              onChange={(e) => setLine(e.target.value)}
            />
            <p className="text-xs text-muted-foreground">
              The room hears it after the system line.
            </p>
          </div>
          <p className="text-xs text-muted-foreground">
            <b>Rule:</b> items given up leave play; their design is kept. Each item with points
            rolls and may earn no favor.
          </p>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setOpen(false)}>
              Close
            </Button>
            <Button type="submit" disabled={chosen.length === 0 || mutation.isPending}>
              {mutation.isPending ? 'Sacrificing…' : 'Sacrifice'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

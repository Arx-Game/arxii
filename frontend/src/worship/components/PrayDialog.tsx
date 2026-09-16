/**
 * PrayDialog (#3779) — the owner's freeform prayer to a being.
 *
 * A prayer is a message, not a mechanic: the dialog says so, and the result line is whatever
 * the action answered (an act of devotion at a holy site, a god answering in dire straits, or
 * simply "You pray"). Dispatches `pray` as the character.
 */

import { useState } from 'react';
import { toast } from 'sonner';
import { useWorshippedBeings } from '@/character-creation/queries';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { usePrayMutation } from '../queries';

interface PrayDialogProps {
  characterId: number;
  /** The character's public being, preselected when set. */
  defaultBeingId?: number | null;
}

export function PrayDialog({ characterId, defaultBeingId }: PrayDialogProps) {
  const [open, setOpen] = useState(false);
  const [beingId, setBeingId] = useState<string>(defaultBeingId ? String(defaultBeingId) : '');
  const [text, setText] = useState('');
  const { data: beings } = useWorshippedBeings();
  const mutation = usePrayMutation(characterId);

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    const words = text.trim();
    if (!beingId) {
      toast.error('Choose whom you pray to.');
      return;
    }
    if (!words) {
      toast.error('A prayer needs words.');
      return;
    }
    mutation.mutate(
      { being: Number(beingId), text: words },
      {
        onSuccess: (result) => {
          if (result.success === false) {
            toast.error(result.message);
            return;
          }
          toast.success(result.message);
          setText('');
          setOpen(false);
        },
        onError: (error: Error) => toast.error(error.message),
      }
    );
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm" data-testid="pray-button">
          Pray
        </Button>
      </DialogTrigger>
      <DialogContent>
        <form onSubmit={handleSubmit} className="space-y-4">
          <DialogHeader>
            <DialogTitle>Pray</DialogTitle>
            <DialogDescription>
              Your own words, to a god. Prayers are read by staff and may be answered; they change
              nothing by themselves.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label htmlFor="pray-being">To</Label>
            <Select value={beingId} onValueChange={setBeingId}>
              <SelectTrigger id="pray-being">
                <SelectValue placeholder="Choose a being" />
              </SelectTrigger>
              <SelectContent>
                {(beings ?? []).map((being) => (
                  <SelectItem key={being.id} value={String(being.id)}>
                    {being.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label htmlFor="pray-text">Words</Label>
            <Textarea
              id="pray-text"
              value={text}
              onChange={(event) => setText(event.target.value)}
              rows={5}
              maxLength={2000}
            />
          </div>
          <DialogFooter>
            <Button type="submit" disabled={mutation.isPending}>
              {mutation.isPending ? 'Praying…' : 'Pray'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

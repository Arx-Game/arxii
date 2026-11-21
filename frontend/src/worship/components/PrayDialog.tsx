/**
 * PrayDialog (#3779, #4349) — the owner's freeform prayer to a being.
 *
 * The result line is whatever the action answered. At a holy site of the being the dialog also
 * takes the action points to spend praying (favor is earned by them, up to the week's limit);
 * with characters present it can pray for one of them, who is in dire straits. Dispatches
 * `pray` as the character.
 */

import { useState } from 'react';
import { toast } from 'sonner';
import { useWorshippedBeings } from '@/character-creation/queries';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  NO_DESCRIPTION,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { usePrayMutation } from '../queries';
import type { PrayerTarget } from '../types';

interface PrayDialogProps {
  characterId: number;
  /** The character's public being, preselected when set. */
  defaultBeingId?: number | null;
  /** At a holy site of the being: what may still be spent praying this week. */
  site?: { apLeft: number; apCap: number } | null;
  /** Characters present who can be prayed for. */
  others?: PrayerTarget[];
  /** The trigger's label; "Pray" unless the dialog is only for praying for someone. */
  triggerLabel?: string;
  /** True when the prayer must be for one of `others`. */
  forRequired?: boolean;
}

const YOURSELF = 'self';

export function PrayDialog({
  characterId,
  defaultBeingId,
  site = null,
  others = [],
  triggerLabel = 'Pray',
  forRequired = false,
}: PrayDialogProps) {
  const [open, setOpen] = useState(false);
  const [beingId, setBeingId] = useState<string>(defaultBeingId ? String(defaultBeingId) : '');
  const [text, setText] = useState('');
  const [ap, setAp] = useState('');
  const [forPersona, setForPersona] = useState<string>(
    forRequired && others[0] ? String(others[0].personaId) : YOURSELF
  );
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
    if (forRequired && forPersona === YOURSELF) {
      toast.error('Choose whom you pray for.');
      return;
    }
    const points = Math.floor(Number(ap));
    if (site && ap !== '' && (!Number.isFinite(points) || points < 0 || points > site.apLeft)) {
      toast.error(`Spend between 0 and ${site.apLeft} AP.`);
      return;
    }
    mutation.mutate(
      {
        being: Number(beingId),
        text: words,
        ap: site && points > 0 ? points : undefined,
        onBehalfOfPersonaId: forPersona === YOURSELF ? undefined : Number(forPersona),
      },
      {
        onSuccess: (result) => {
          if (result.success === false) {
            toast.error(result.message);
            return;
          }
          toast.success(result.message);
          setText('');
          setAp('');
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
          {triggerLabel}
        </Button>
      </DialogTrigger>
      <DialogContent {...NO_DESCRIPTION}>
        <form onSubmit={handleSubmit} className="space-y-4">
          <DialogHeader>
            <DialogTitle>Pray</DialogTitle>
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
          {others.length > 0 && (
            <div className="space-y-2">
              <Label htmlFor="pray-for">For</Label>
              <Select value={forPersona} onValueChange={setForPersona}>
                <SelectTrigger id="pray-for">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {!forRequired && <SelectItem value={YOURSELF}>Myself</SelectItem>}
                  {others.map((other) => (
                    <SelectItem key={other.personaId} value={String(other.personaId)}>
                      {other.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}
          {site && (
            <div className="space-y-2">
              <Label htmlFor="pray-ap">AP</Label>
              <Input
                id="pray-ap"
                type="number"
                min={0}
                max={site.apLeft}
                value={ap}
                onChange={(event) => setAp(event.target.value)}
              />
              <p className="text-xs text-muted-foreground" data-testid="pray-ap-left">
                {site.apLeft} of {site.apCap} left this week
              </p>
            </div>
          )}
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

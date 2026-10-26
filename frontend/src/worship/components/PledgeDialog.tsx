/**
 * PledgeDialog (#4333) — Pledge yourself to a being: pick one of its pledge types and see, as
 * separate labelled parts, the pledge's staff-authored text, its favor target, and the
 * system-generated list of what earns favor for this character with their earning rate. An
 * optional prayer goes with it (stored as a Prayer). Dispatches `pledge_take` as the character.
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
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { usePledges, useServiceTerms, useTakePledge } from '../queries';
import { ServiceTermsList } from './ServiceTermsList';

interface PledgeDialogProps {
  /** The acting character's sheet (= ObjectDB) pk. */
  characterId: number;
  /** Preselects a being; with `fixedBeing`, the being cannot be changed (a shrine's card). */
  defaultBeingId?: number | null;
  fixedBeing?: boolean;
  /** Read the terms for this sheet (the sheet page) rather than the tab's acting character. */
  sheetId?: number | null;
  size?: 'sm' | 'default';
  variant?: 'default' | 'outline';
}

function weeksLabel(weeks: number): string {
  return weeks === 1 ? 'one game week' : `${weeks} game weeks`;
}

export function PledgeDialog({
  characterId,
  defaultBeingId,
  fixedBeing = false,
  sheetId,
  size = 'sm',
  variant = 'default',
}: PledgeDialogProps) {
  const [open, setOpen] = useState(false);
  const [beingId, setBeingId] = useState<string>(defaultBeingId ? String(defaultBeingId) : '');
  const [pledgeId, setPledgeId] = useState<string>('');
  const [prayer, setPrayer] = useState('');
  const { data: beings } = useWorshippedBeings();
  const being = beingId ? Number(beingId) : null;
  const { data: pledges } = usePledges(being, open);
  const { data: terms } = useServiceTerms(being, { sheetId, enabled: open });
  const mutation = useTakePledge(characterId);
  const beingName =
    (beings ?? []).find((row) => row.id === being)?.name ?? terms?.being_name ?? 'a being';
  const chosen = (pledges ?? []).find((row) => String(row.id) === pledgeId) ?? null;

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!chosen) {
      toast.error('Choose a pledge.');
      return;
    }
    mutation.mutate(
      { pledge: chosen.id, prayer: prayer.trim() },
      {
        onSuccess: (result) => {
          if (result.success === false) {
            toast.error(result.message);
            return;
          }
          toast.success(result.message);
          setPrayer('');
          setOpen(false);
        },
        onError: (error: Error) => toast.error(error.message),
      }
    );
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant={variant} size={size} data-testid="pledge-button">
          Pledge yourself
        </Button>
      </DialogTrigger>
      <DialogContent {...NO_DESCRIPTION} className="max-h-[90vh] overflow-y-auto sm:max-w-xl">
        <form onSubmit={handleSubmit} className="space-y-4">
          <DialogHeader>
            <DialogTitle>Pledge yourself to {beingName}</DialogTitle>
          </DialogHeader>
          {!fixedBeing && (
            <div className="space-y-2">
              <Label htmlFor="pledge-being">To</Label>
              <Select
                value={beingId}
                onValueChange={(value) => {
                  setBeingId(value);
                  setPledgeId('');
                }}
              >
                <SelectTrigger id="pledge-being">
                  <SelectValue placeholder="Choose a being" />
                </SelectTrigger>
                <SelectContent>
                  {(beings ?? []).map((row) => (
                    <SelectItem key={row.id} value={String(row.id)}>
                      {row.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}
          {being != null && (
            <>
              <div className="space-y-2">
                <span className="text-sm font-medium">
                  Pledge type <span className="text-muted-foreground">(staff-authored text)</span>
                </span>
                {(pledges ?? []).length === 0 ? (
                  <p className="text-sm text-muted-foreground" data-testid="no-pledges">
                    {beingName} offers no pledge.
                  </p>
                ) : (
                  <RadioGroup value={pledgeId} onValueChange={setPledgeId} className="space-y-2">
                    {(pledges ?? []).map((row) => (
                      <div key={row.id} className="flex items-start gap-2">
                        <RadioGroupItem
                          value={String(row.id)}
                          id={`pledge-${row.id}`}
                          className="mt-1"
                        />
                        <Label htmlFor={`pledge-${row.id}`} className="space-y-1 font-normal">
                          <span className="block font-medium">{row.name}</span>
                          {row.description && (
                            <span className="block text-sm text-muted-foreground">
                              {row.description}
                            </span>
                          )}
                        </Label>
                      </div>
                    ))}
                  </RadioGroup>
                )}
              </div>
              {chosen && (
                <div className="space-y-1" data-testid="favor-target">
                  <span className="text-sm font-medium">
                    Favor target <span className="text-muted-foreground">(staff-authored)</span>
                  </span>
                  <p className="text-sm">
                    <b>{chosen.favor_target} favor</b> earned with {beingName} within{' '}
                    <b>{weeksLabel(chosen.span_weeks)}</b> of pledging. Closed with{' '}
                    {chosen.closing_rite_name}.
                  </p>
                </div>
              )}
              {terms && (
                <div className="space-y-1">
                  <span className="text-sm font-medium">
                    What earns favor with {beingName} for you{' '}
                    <span className="text-muted-foreground">(system-generated)</span>
                  </span>
                  <ServiceTermsList terms={terms} />
                </div>
              )}
              <div className="space-y-2">
                <Label htmlFor="pledge-prayer">
                  Prayer{' '}
                  <span className="font-normal text-muted-foreground">
                    (optional, player-written, stored as a Prayer)
                  </span>
                </Label>
                <Textarea
                  id="pledge-prayer"
                  value={prayer}
                  onChange={(event) => setPrayer(event.target.value)}
                  rows={3}
                  maxLength={2000}
                />
              </div>
            </>
          )}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setOpen(false)}>
              Close
            </Button>
            <Button type="submit" disabled={!chosen || mutation.isPending}>
              {mutation.isPending ? 'Pledging…' : 'Pledge'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

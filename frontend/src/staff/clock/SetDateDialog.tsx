import { useEffect, useMemo, useState } from 'react';

import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  NO_DESCRIPTION,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { extractErrorMessage } from '@/lib/errors';

import { type GameDate, describeJump, gameDateOf, isValidGameDate, toIso } from './clockDate';
import { useJumpPreview, useSetClockDate } from './queries';
import type { AgeHandling, ClockJumpPreview, ClockState } from './types';

const SELECT_CLASS =
  'h-9 w-full rounded-md border border-input bg-background px-2 text-sm ' +
  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring';

function years(count: number): string {
  return `${count} ${count === 1 ? 'year' : 'years'}`;
}

function countOf(count: number, one: string, many: string): string {
  return `${count} ${count === 1 ? one : many}`;
}

/** What "Characters age" does, in the words of this jump. */
function agedText(preview: ClockJumpPreview): string {
  const people = countOf(preview.characters_with_birth_year, 'character', 'characters');
  if (preview.year_shift === 0) {
    return `Nobody's age in years changes. Each of the ${people} with a birth year has any birthday that falls in between.`;
  }
  return `Each of the ${people} with a birth year becomes ${years(preview.year_shift)} older and matures by the birthdays skipped. Nobody dies because of the jump.`;
}

/** What "Characters keep their ages" does, in the words of this jump. */
function keptText(preview: ClockJumpPreview): string {
  if (preview.year_shift === 0) {
    return 'The calendar moves and nobody ages. Birthdays that fall in between are not counted.';
  }
  const way = preview.year_shift > 0 ? 'forward' : 'back';
  return `The calendar moves and nobody ages. Every birth year moves ${way} by ${Math.abs(preview.year_shift)}.`;
}

interface SetDateDialogProps {
  clock: ClockState;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/**
 * Set the game's date and time (#5248). A change forward asks whether characters age
 * with the calendar or keep their ages; a change back always keeps them. The sentence
 * and the counts come from the server's preview, which writes nothing.
 */
export function SetDateDialog({ clock, open, onOpenChange }: SetDateDialogProps) {
  const current = useMemo(() => gameDateOf(clock), [clock]);
  const [date, setDate] = useState<GameDate>(current);
  const [ageHandling, setAgeHandling] = useState<AgeHandling | null>(null);
  const [reason, setReason] = useState('');
  const mutation = useSetClockDate();
  const { reset } = mutation;

  // Each opening starts from the date the clock shows now.
  useEffect(() => {
    if (open) {
      setDate(current);
      setAgeHandling(null);
      setReason('');
      reset();
    }
    // `current` is read at the moment of opening only: a running clock moves on behind
    // the dialog, and that must not rewrite what staff are typing.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, reset]);

  const years = { min: clock.min_year, max: clock.max_year };
  const inRange = date.year >= years.min && date.year <= years.max;
  const valid = isValidGameDate(date, years);
  const jump = valid ? describeJump(current, date) : null;
  const { data: preview, error: previewError } = useJumpPreview(
    open && valid && jump ? toIso(date) : null
  );
  const back = preview?.direction === 'back';
  const chosen: AgeHandling | null = back ? 'kept' : ageHandling;
  const ready = Boolean(jump && preview && chosen && reason.trim());

  const setField = (field: keyof GameDate, raw: string) => {
    const value = /^\d+$/.test(raw) ? Number.parseInt(raw, 10) : Number.NaN;
    setDate((previous) => ({ ...previous, [field]: value }));
    // A choice was made about one jump. A different date is a different jump, so the
    // choice is asked again rather than carried over.
    setAgeHandling(null);
  };
  const shown = (value: number) => (Number.isNaN(value) ? '' : String(value));

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    if (!ready || !chosen) return;
    mutation.mutate(
      { ic_datetime: toIso(date), reason: reason.trim(), age_handling: chosen },
      { onSuccess: () => onOpenChange(false) }
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent {...NO_DESCRIPTION} className="max-w-xl">
        <DialogHeader>
          <DialogTitle>Set the date</DialogTitle>
        </DialogHeader>
        <form onSubmit={submit} className="space-y-4">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-6">
            <div className="space-y-1">
              <Label htmlFor="clock-year">Year</Label>
              <Input
                id="clock-year"
                inputMode="numeric"
                value={shown(date.year)}
                onChange={(event) => setField('year', event.target.value)}
              />
            </div>
            <div className="space-y-1 sm:col-span-2">
              <Label htmlFor="clock-month">Month</Label>
              <select
                id="clock-month"
                className={SELECT_CLASS}
                value={date.month}
                onChange={(event) => setField('month', event.target.value)}
              >
                {clock.month_names.map((name, index) => (
                  <option key={name} value={index + 1}>
                    {name}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-1">
              <Label htmlFor="clock-day">Day</Label>
              <Input
                id="clock-day"
                inputMode="numeric"
                value={shown(date.day)}
                onChange={(event) => setField('day', event.target.value)}
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="clock-hour">Hour</Label>
              <Input
                id="clock-hour"
                inputMode="numeric"
                value={shown(date.hour)}
                onChange={(event) => setField('hour', event.target.value)}
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="clock-minute">Minute</Label>
              <Input
                id="clock-minute"
                inputMode="numeric"
                value={shown(date.minute)}
                onChange={(event) => setField('minute', event.target.value)}
              />
            </div>
          </div>

          {!valid && (
            <p role="alert" className="text-sm text-destructive">
              {inRange || Number.isNaN(date.year)
                ? 'That date does not exist.'
                : `The year must be between ${years.min} and ${years.max}.`}
            </p>
          )}

          {jump && preview && (
            <>
              <p className="border-l-2 pl-3 text-sm">
                This moves the world <strong>{jump}</strong>, from {preview.current_date_display}.
              </p>

              {back ? (
                <p className="text-sm">
                  <strong>Characters keep their ages.</strong> {keptText(preview)} A calendar cannot
                  make anyone younger.
                </p>
              ) : (
                <RadioGroup
                  aria-label="What happens to characters"
                  value={ageHandling ?? ''}
                  onValueChange={(value) => setAgeHandling(value as AgeHandling)}
                >
                  <label
                    htmlFor="clock-aged"
                    className="flex cursor-pointer items-start gap-3 rounded-md border p-3"
                  >
                    <RadioGroupItem id="clock-aged" value="aged" className="mt-1" />
                    <span className="text-sm">
                      <span className="block font-medium">Characters age</span>
                      <span className="text-muted-foreground">{agedText(preview)}</span>
                    </span>
                  </label>
                  <label
                    htmlFor="clock-kept"
                    className="flex cursor-pointer items-start gap-3 rounded-md border p-3"
                  >
                    <RadioGroupItem id="clock-kept" value="kept" className="mt-1" />
                    <span className="text-sm">
                      <span className="block font-medium">Characters keep their ages</span>
                      <span className="text-muted-foreground">{keptText(preview)}</span>
                    </span>
                  </label>
                </RadioGroup>
              )}
            </>
          )}

          {previewError && (
            <p role="alert" className="text-sm text-destructive">
              {extractErrorMessage(previewError)}
            </p>
          )}

          <div className="space-y-1">
            <Label htmlFor="clock-reason">Reason</Label>
            <Input
              id="clock-reason"
              value={reason}
              maxLength={500}
              onChange={(event) => setReason(event.target.value)}
            />
          </div>

          {jump && preview && (
            <ul className="space-y-1 text-sm text-muted-foreground">
              <li>
                {clock.paused
                  ? 'The clock is paused and stays paused.'
                  : 'The clock keeps running from the new date.'}
              </li>
              {preview.upcoming_events > 0 && (
                <li>
                  {countOf(preview.upcoming_events, 'upcoming event moves', 'upcoming events move')}{' '}
                  with it.
                </li>
              )}
              {preview.heritages_not_yet_appeared.map((name) => (
                <li key={name} className="text-amber-700 dark:text-amber-400">
                  {name} first appeared after this date. Character creation would offer {name} at
                  the youngest age only.
                </li>
              ))}
            </ul>
          )}

          {mutation.error && (
            <p role="alert" className="text-sm text-destructive">
              {extractErrorMessage(mutation.error)}
            </p>
          )}

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={!ready || mutation.isPending}>
              {jump ? `Move the world ${jump}` : 'Set the date'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

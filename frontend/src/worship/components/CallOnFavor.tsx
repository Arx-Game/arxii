/**
 * CallOnFavor (#4333) — the Call on favor control beside a check.
 *
 * Before a check (a mission option, a scene check, a scene action) a character may call on a
 * being they have favor with. The picker shows, per being, how hard the invocation check is
 * for them and why (each ease, in points), the bonus each result gives the check, and their
 * uses left this week; a being they cannot call on is listed greyed with the reason. The
 * player may add one line of how it shows, which the room sees (a secret faith's room line
 * names no being and drops it).
 *
 * The choice is held by the caller and sent with the check; nothing rolls here. Once chosen,
 * the control reads "Invoking Ombrin first (Easy)" with a way to take it back.
 */

import { useMemo, useState } from 'react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { Textarea } from '@/components/ui/textarea';
import { useInvocationOptions } from '../queries';
import { bonusLine } from '../invocationText';
import type { InvocationChoice, InvocationOption, WornMeaning } from '../types';

/** The line a player may attach is one line, matching the server's limit. */
const LINE_MAX_LENGTH = 200;

interface CallOnFavorProps {
  /** The choice already made for this check, or null. */
  value: InvocationChoice | null;
  onChange: (choice: InvocationChoice | null) => void;
  /** The acting character's roster entry; omitted, this tab's browsing identity. */
  entryId?: number | null;
  disabled?: boolean;
  /**
   * Render the picker in place rather than in a dialog: for a host that is itself a popover,
   * where a dialog would close it.
   */
  inline?: boolean;
}

function DifficultyBreakdown({ option }: { option: InvocationOption }) {
  const difficulty = option.difficulty;
  if (!difficulty) return null;
  return (
    <div className="space-y-1 text-sm" data-testid="invocation-difficulty">
      <div className="flex justify-between gap-2 border-b border-dotted py-0.5">
        <span>Base</span>
        <span className="font-semibold tabular-nums text-amber-700 dark:text-amber-400">
          {difficulty.base_band_label}, {difficulty.base_points}
        </span>
      </div>
      {difficulty.eases.map((ease) => (
        <div key={ease.label} className="flex justify-between gap-2 border-b border-dotted py-0.5">
          <span>{ease.label}</span>
          <span
            className={
              ease.points
                ? 'font-semibold tabular-nums text-amber-700 dark:text-amber-400'
                : 'tabular-nums text-muted-foreground'
            }
          >
            {ease.points ? `-${ease.points}` : '0'}
          </span>
        </div>
      ))}
      <div className="flex justify-between gap-2 py-0.5">
        <span className="font-semibold">Result (eases add; 15 points is one band)</span>
        <span
          className="font-semibold tabular-nums text-amber-700 dark:text-amber-400"
          data-testid="invocation-result"
        >
          {difficulty.points}, {difficulty.band_label}
        </span>
      </div>
    </div>
  );
}

/**
 * The worn pieces carrying a facet the selected being favors (#4520): what each means to
 * the wearer, whether it counts, and the ease it gives. The wearer sees her own points; a
 * bought piece with no history is listed as adding nothing.
 */
function WornPieces({ worn, beingName }: { worn: WornMeaning; beingName: string }) {
  if (worn.pieces.length === 0) return null;
  return (
    <div className="space-y-1" data-testid="invocation-worn">
      <Label>What you wear that {beingName} favors</Label>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="text-xs text-muted-foreground">
              <th className="py-0.5 pr-2 font-normal">Worn piece</th>
              <th className="py-0.5 pr-2 font-normal">What it means</th>
              <th className="py-0.5 font-normal">Counts</th>
            </tr>
          </thead>
          <tbody>
            {worn.pieces.map((piece) => (
              <tr
                key={`${piece.item_name}-${piece.facet_name}`}
                className="border-t border-dotted align-top"
                data-testid="invocation-worn-piece"
              >
                <td className="py-1 pr-2">{piece.item_name}</td>
                <td className="py-1 pr-2">
                  <span className="flex flex-wrap gap-1">
                    {piece.signals.length === 0 ? (
                      <Badge variant="outline" className="opacity-60">
                        bought; no history beyond holding it
                      </Badge>
                    ) : (
                      piece.signals.map((signal) => (
                        <Badge key={signal.kind} variant="secondary">
                          {signal.kind_name.toLowerCase()}
                        </Badge>
                      ))
                    )}
                    <Badge variant="outline">{piece.facet_name}, favored</Badge>
                  </span>
                </td>
                <td className="py-1 tabular-nums" data-testid="invocation-worn-counts">
                  {piece.counted
                    ? `${piece.points} points x ${piece.ease_per_point} = eased ${piece.ease}`
                    : '0'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-muted-foreground" data-testid="invocation-worn-note">
        Up to {worn.items_counted_max} worn pieces count, and the ease from what you wear is capped
        at {worn.ease_cap}
        {worn.raw_ease > worn.ease ? ` (these would ease ${worn.raw_ease})` : ''}.
        {worn.earning_percent
          ? ` Earning rate with ${beingName} while you wear these: 100% + ${worn.earning_percent}%.`
          : ''}
      </p>
    </div>
  );
}

function CallOnFavorPicker({
  entryId,
  onConfirm,
  onClose,
}: {
  entryId?: number | null;
  onConfirm: (choice: InvocationChoice) => void;
  onClose: () => void;
}) {
  const { data, isLoading, error } = useInvocationOptions({ entryId });
  const beings = useMemo(() => data?.beings ?? [], [data]);
  const invocable = beings.filter((option) => option.can_invoke);
  const [selectedId, setSelectedId] = useState<string>('');
  const [line, setLine] = useState('');
  const selected =
    invocable.find((option) => String(option.being_id) === selectedId) ?? invocable[0] ?? null;
  const perWeek = invocable[0]?.uses_per_week ?? beings[0]?.uses_per_week;

  function confirm() {
    if (!selected?.difficulty) return;
    onConfirm({
      beingId: selected.being_id,
      beingName: selected.being_name,
      bandLabel: selected.difficulty.band_label,
      line: line.trim(),
    });
    onClose();
  }

  return (
    <div className="space-y-4" data-testid="call-on-favor-picker">
      {isLoading ? <p className="text-sm text-muted-foreground">…</p> : null}
      {error ? <p className="text-sm text-destructive">{(error as Error).message}</p> : null}
      {data && beings.length === 0 ? (
        <p className="text-sm text-muted-foreground" data-testid="invocation-none">
          You have no favor with any being to call on.
        </p>
      ) : null}
      {beings.length > 0 ? (
        <>
          <div className="space-y-2">
            <Label>Being</Label>
            <RadioGroup
              value={selected ? String(selected.being_id) : ''}
              onValueChange={setSelectedId}
              data-testid="invocation-beings"
            >
              {beings.map((option) =>
                option.can_invoke && option.difficulty ? (
                  <label
                    key={option.being_id}
                    className="flex flex-wrap items-center gap-2 text-sm"
                    data-testid="invocation-being"
                  >
                    <RadioGroupItem value={String(option.being_id)} />
                    <span className="font-semibold">{option.being_name}</span>
                    <Badge variant="outline">{option.difficulty.band_label}</Badge>
                    <span className="text-xs text-muted-foreground">
                      {option.uses_left} of {option.uses_per_week} left this week
                    </span>
                  </label>
                ) : (
                  <div
                    key={option.being_id}
                    className="rounded border px-2 py-1 text-xs text-muted-foreground opacity-60"
                    data-testid="invocation-being-refused"
                  >
                    {option.being_name}: {option.refusal}
                  </div>
                )
              )}
            </RadioGroup>
          </div>
          {selected ? (
            <div className="space-y-2">
              <Label>Invocation difficulty for {selected.being_name}</Label>
              <DifficultyBreakdown option={selected} />
            </div>
          ) : null}
          {selected?.worn ? (
            <WornPieces worn={selected.worn} beingName={selected.being_name} />
          ) : null}
          <div className="space-y-1">
            <Label>Bonus to the next check, by result</Label>
            <p className="text-sm" data-testid="invocation-bonuses">
              {bonusLine(data?.bonuses ?? [])}
            </p>
          </div>
          <div className="space-y-1">
            <Label htmlFor="invocation-line">
              How it shows{' '}
              <span className="font-normal text-muted-foreground">(optional, one line)</span>
            </Label>
            <Textarea
              id="invocation-line"
              value={line}
              onChange={(event) => setLine(event.target.value.replace(/\n/g, ' '))}
              maxLength={LINE_MAX_LENGTH}
              rows={2}
              data-testid="invocation-line"
            />
          </div>
          {perWeek ? (
            <p className="text-xs text-muted-foreground">
              <span className="font-semibold">Rules:</span> favor is not spent. A failed invocation
              still uses one of this week&apos;s {perWeek}. One being per check.
            </p>
          ) : null}
        </>
      ) : null}
      <div className="flex justify-end gap-2">
        <Button type="button" variant="outline" size="sm" onClick={onClose}>
          Close
        </Button>
        <Button
          type="button"
          size="sm"
          onClick={confirm}
          disabled={!selected}
          data-testid="invocation-confirm"
        >
          {selected ? `Call on ${selected.being_name}` : 'Call on favor'}
        </Button>
      </div>
    </div>
  );
}

/**
 * The control itself: a "Call on favor" button, or, once chosen, what will be invoked with a
 * button to take it back.
 */
export function CallOnFavor({
  value,
  onChange,
  entryId,
  disabled,
  inline = false,
}: CallOnFavorProps) {
  const [open, setOpen] = useState(false);
  const picker = open ? (
    <CallOnFavorPicker entryId={entryId} onConfirm={onChange} onClose={() => setOpen(false)} />
  ) : null;
  return (
    <>
      {value ? (
        <span className="inline-flex items-center gap-2 text-xs" data-testid="invocation-chosen">
          <span className="text-muted-foreground">
            Invoking {value.beingName} first ({value.bandLabel})
          </span>
          <Button
            type="button"
            size="sm"
            variant="ghost"
            className="h-6 px-2 text-xs"
            onClick={() => onChange(null)}
            disabled={disabled}
            data-testid="invocation-clear"
          >
            Don&apos;t call
          </Button>
        </span>
      ) : (
        <Button
          type="button"
          size="sm"
          variant="outline"
          className="h-7 text-xs"
          onClick={() => setOpen((was) => !was)}
          disabled={disabled}
          data-testid="call-on-favor"
        >
          Call on favor
        </Button>
      )}
      {inline ? (
        picker && <div className="w-full rounded border p-3">{picker}</div>
      ) : (
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogContent
            className="max-w-lg"
            aria-describedby={undefined}
            data-testid="call-on-favor-dialog"
          >
            <DialogHeader>
              <DialogTitle>Call on favor</DialogTitle>
            </DialogHeader>
            {picker}
          </DialogContent>
        </Dialog>
      )}
    </>
  );
}

/**
 * ImbuePanel — spend resonance to advance a Thread.
 *
 * Shows a stepper for `amount` (0..balance). Amount=0 is valid (probes blocked_by).
 * On success, displays the shown levels climbed and the shown level (threads are stored
 * x10), and blocked_by.
 * On error, shows the typed user_message inline. When the imbue opened new vow pick
 * levels (#4929), "Choose picks" leads to the character's sheet, where they are chosen.
 */
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { useMyRosterEntriesQuery } from '@/roster/queries';
import { extractErrorMessage } from '@/lib/errors';
import { useImbueThread } from '../../queries';
import type { ImbueResponse, Thread } from '../../types';

interface ImbuePanelProps {
  thread: Thread;
  /** Spendable resonance balance for this thread's resonance. */
  balance: number;
  characterSheetId: number;
  onResult?: (result: ImbueResponse) => void;
}

/**
 * The rite's own lines. The message ends with a vow's new-picks lines (telnet reads them
 * there); the web draws those from `new_picks` instead, with the points in bold.
 */
function riteLines(result: ImbueResponse): string[] {
  const count = result.new_picks?.length ?? 0;
  const lines = (result.message ?? '').split('\n').filter(Boolean);
  return count > 0 ? lines.slice(0, -count) : lines;
}

function pointsLabel(points: number): string {
  return `${points} ${points === 1 ? 'pt' : 'pts'}`;
}

/**
 * The shown level and how many shown levels the imbue climbed. Threads are stored x10
 * (#4585), so `levels_gained` and `new_level` are never the numbers a player reads.
 */
function shownClimb(result: ImbueResponse): { level: number; gained: number } | null {
  if (result.new_level === undefined) return null;
  const level = Math.floor(result.new_level / 10);
  const before = Math.floor((result.new_level - (result.levels_gained ?? 0)) / 10);
  return { level, gained: level - before };
}

/** The sheet's Ties section, where the vow's picks are chosen. */
function ChoosePicksLink({ characterSheetId }: { characterSheetId: number }) {
  const { data: entries } = useMyRosterEntriesQuery();
  const entry = entries?.find((row) => row.character_id === characterSheetId);
  if (!entry) return null;
  return (
    <Button asChild size="sm" variant="outline">
      <Link to={`/characters/${entry.id}?section=ties`}>Choose picks</Link>
    </Button>
  );
}

export function ImbuePanel({ thread, balance, characterSheetId, onResult }: ImbuePanelProps) {
  const [amount, setAmount] = useState(1);
  const [lastResult, setLastResult] = useState<ImbueResponse | null>(null);

  const { mutate, isPending, error, isError } = useImbueThread();
  const climb = lastResult ? shownClimb(lastResult) : null;

  const handleDecrement = () => setAmount((a) => Math.max(0, a - 1));
  const handleIncrement = () => setAmount((a) => Math.min(balance, a + 1));

  const handleImbue = () => {
    setLastResult(null);
    mutate(
      { characterSheetId, threadId: thread.id, amount },
      {
        onSuccess: (result) => {
          setLastResult(result);
          onResult?.(result);
        },
      }
    );
  };

  return (
    <div className="space-y-3 rounded-lg border p-4" data-testid="imbue-panel">
      <h3 className="text-sm font-semibold">Imbue Thread</h3>
      <p className="text-sm text-muted-foreground">
        Spend resonance to advance this thread. Available balance:{' '}
        <span className="font-medium tabular-nums">{balance}</span>
      </p>

      {/* Amount stepper */}
      <div className="flex items-center gap-3">
        <span className="text-sm">Amount:</span>
        <div className="flex items-center gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={handleDecrement}
            disabled={amount <= 0 || isPending}
            aria-label="Decrease amount"
            data-testid="imbue-decrement"
          >
            -
          </Button>
          <span className="w-8 text-center font-medium tabular-nums" data-testid="imbue-amount">
            {amount}
          </span>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={handleIncrement}
            disabled={amount >= balance || isPending}
            aria-label="Increase amount"
            data-testid="imbue-increment"
          >
            +
          </Button>
        </div>
      </div>

      {/* Action button */}
      <Button type="button" onClick={handleImbue} disabled={isPending} data-testid="imbue-button">
        {isPending ? 'Imbuing…' : 'Imbue'}
      </Button>

      {/* Error state */}
      {isError && (
        <p className="text-sm text-destructive" data-testid="imbue-error" role="alert">
          {extractErrorMessage(error)}
        </p>
      )}

      {/* Success summary */}
      {lastResult && lastResult.success && (
        <div className="space-y-1 rounded-md bg-muted p-3 text-sm" data-testid="imbue-result">
          {riteLines(lastResult).length > 0 && (
            <p className="whitespace-pre-line text-muted-foreground">
              {riteLines(lastResult).join('\n')}
            </p>
          )}
          {(lastResult.new_picks?.length ?? 0) > 0 && (
            <div
              className="flex flex-wrap items-center justify-between gap-2 border-l-2 border-primary py-1 pl-3"
              data-testid="imbue-new-picks"
            >
              <span className="flex flex-col">
                {lastResult.new_picks?.map((opened) => (
                  <span key={opened.level}>
                    Vow level {opened.level}: <b>{pointsLabel(opened.points)}</b> of new picks
                  </span>
                ))}
              </span>
              <ChoosePicksLink characterSheetId={characterSheetId} />
            </div>
          )}
          {climb && (
            <p data-testid="imbue-levels-gained">
              {climb.gained > 0 ? (
                <>
                  <span className="font-medium">{climb.gained}</span>{' '}
                  {climb.gained === 1 ? 'level' : 'levels'} gained, now level{' '}
                </>
              ) : (
                'Now level '
              )}
              <span className="font-medium tabular-nums">{climb.level}</span>
            </p>
          )}
          {lastResult.blocked_by && lastResult.blocked_by !== 'NONE' && (
            <p className="text-yellow-700 dark:text-yellow-400" data-testid="imbue-blocked-by">
              Blocked by: {lastResult.blocked_by.replace(/_/g, ' ').toLowerCase()}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

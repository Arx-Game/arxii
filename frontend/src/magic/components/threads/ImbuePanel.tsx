/**
 * ImbuePanel — spend resonance to advance a Thread.
 *
 * Shows a stepper for `amount` (0..balance). Amount=0 is valid (probes blocked_by).
 * On success, displays an inline summary of levels_gained, new_level, and blocked_by.
 * On error, shows the typed user_message inline.
 */
import { useState } from 'react';
import { Button } from '@/components/ui/button';
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
 * Parse a user-facing error message from a mutation error.
 * Prefers `error.message` when available.
 */
function extractErrorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  return 'An unexpected error occurred.';
}

export function ImbuePanel({ thread, balance, characterSheetId, onResult }: ImbuePanelProps) {
  const [amount, setAmount] = useState(1);
  const [lastResult, setLastResult] = useState<ImbueResponse | null>(null);

  const { mutate, isPending, error, isError } = useImbueThread();

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
            –
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
          {lastResult.message && <p className="text-muted-foreground">{lastResult.message}</p>}
          {lastResult.levels_gained !== undefined && (
            <p data-testid="imbue-levels-gained">
              <span className="font-medium">{lastResult.levels_gained}</span>{' '}
              {lastResult.levels_gained === 1 ? 'level' : 'levels'} gained
              {lastResult.new_level !== undefined && (
                <>
                  {' '}
                  &mdash; now level{' '}
                  <span className="font-medium tabular-nums">
                    {(lastResult.new_level / 10).toFixed(0)}
                  </span>
                </>
              )}
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

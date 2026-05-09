/**
 * XPLockBoundaryPanel — surfaces the next XP-lock boundary for a thread.
 *
 * Renders nothing when:
 *   - prospect is null (no upcoming lock in sight), or
 *   - the thread's level is already past the boundary.
 *
 * Otherwise, shows the boundary level, XP cost, and available XP, plus a
 * [Pay XP to Cross] button that calls useCrossXPLock.
 */
import { Button } from '@/components/ui/button';
import { useCrossXPLock } from '../../queries';
import type { NearXPLockProspect, Thread } from '../../types';

interface XPLockBoundaryPanelProps {
  thread: Thread;
  /** The nearest XP-lock prospect for this thread, or null if none upcoming. */
  prospect: NearXPLockProspect | null;
  /** Account-level available XP. */
  accountAvailableXP: number;
}

export function XPLockBoundaryPanel({
  thread,
  prospect,
  accountAvailableXP,
}: XPLockBoundaryPanelProps) {
  const { mutate, isPending, error, isError } = useCrossXPLock();

  // Render nothing when there's no prospect or the thread has passed this boundary.
  if (!prospect || thread.level >= prospect.boundary_level) {
    return null;
  }

  const canAfford = accountAvailableXP >= prospect.xp_cost;
  const displayBoundaryLevel = prospect.boundary_level / 10;

  const handlePay = () => {
    mutate({ threadId: thread.id, body: { boundary_level: prospect.boundary_level } });
  };

  return (
    <div
      className="space-y-3 rounded-lg border border-yellow-200 bg-yellow-50 p-4 dark:border-yellow-800 dark:bg-yellow-950/20"
      data-testid="xp-lock-boundary-panel"
    >
      <h3 className="text-sm font-semibold text-yellow-800 dark:text-yellow-200">
        XP Lock Boundary
      </h3>
      <p className="text-sm text-yellow-700 dark:text-yellow-300" data-testid="xp-lock-description">
        Crossing level <span className="font-medium tabular-nums">{displayBoundaryLevel}</span>{' '}
        requires <span className="font-medium tabular-nums">{prospect.xp_cost}</span> XP. Available:{' '}
        <span className="font-medium tabular-nums" data-testid="xp-available">
          {accountAvailableXP}
        </span>
      </p>

      {isError && (
        <p className="text-sm text-destructive" data-testid="xp-lock-error" role="alert">
          {error instanceof Error ? error.message : 'Failed to cross XP lock.'}
        </p>
      )}

      <Button
        type="button"
        variant="outline"
        onClick={handlePay}
        disabled={!canAfford || isPending}
        data-testid="xp-lock-pay-button"
      >
        {isPending ? 'Processing…' : 'Pay XP to Cross'}
      </Button>
    </div>
  );
}

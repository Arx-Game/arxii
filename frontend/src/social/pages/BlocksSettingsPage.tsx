/**
 * BlocksSettingsPage (#1278) — the characters you've blocked, with Unblock / Share.
 *
 * Unblock is cron-delayed (the block stays active until the next sweep). Share extends a block to
 * all your characters (they may then realize those characters share a player).
 */
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';

import { useBlocks, useShareBlock, useUnblock } from '../queries';
import type { Block } from '../types';

function BlockRow({ block }: { block: Block }) {
  const unblock = useUnblock();
  const share = useShareBlock();
  return (
    <div
      className="flex items-center justify-between rounded-lg border bg-card p-4"
      data-testid="block-row"
    >
      <div className="space-y-0.5">
        <p className="font-medium">
          {block.blocked_persona_name}
          {block.account_level && (
            <span className="ml-2 text-xs text-muted-foreground">(all my characters)</span>
          )}
        </p>
        {block.reason && <p className="text-xs text-muted-foreground">Reason: {block.reason}</p>}
        {block.pending_removal_at && (
          <p className="text-xs text-amber-600">Unblocking — clears on the next cron cycle.</p>
        )}
      </div>
      <div className="flex gap-2">
        {!block.account_level && (
          <Button
            variant="outline"
            size="sm"
            onClick={() => share.mutate(block.id)}
            disabled={share.isPending}
          >
            Share
          </Button>
        )}
        <Button
          variant="outline"
          size="sm"
          onClick={() => unblock.mutate(block.id)}
          disabled={unblock.isPending || block.pending_removal_at !== null}
        >
          Unblock
        </Button>
      </div>
    </div>
  );
}

export function BlocksSettingsPage() {
  const { data, isLoading } = useBlocks();
  const blocks = data?.results ?? [];
  return (
    <ErrorBoundary>
      <div className="space-y-4">
        <div>
          <h2 className="text-lg font-semibold">Blocked</h2>
          <p className="text-sm text-muted-foreground">
            Unblocking takes a full cron cycle to clear, so blocks are deliberate.
          </p>
        </div>
        {isLoading ? (
          <Skeleton className="h-20 w-full" />
        ) : blocks.length === 0 ? (
          <p className="text-sm text-muted-foreground">You haven't blocked anyone.</p>
        ) : (
          <div className="space-y-3">
            {blocks.map((block) => (
              <BlockRow key={block.id} block={block} />
            ))}
          </div>
        )}
      </div>
    </ErrorBoundary>
  );
}

export default BlocksSettingsPage;

/**
 * MutesSettingsPage (#1278) — the characters you've muted, with per-row Unmute.
 *
 * Mute is one-way and reversible: the muted player is never aware.
 */
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';

import { useMutes, useUnmute } from '../queries';
import type { Mute } from '../types';

function MuteRow({ mute }: { mute: Mute }) {
  const unmute = useUnmute();
  const scope = [mute.mute_ic && 'IC', mute.mute_ooc && 'OOC'].filter(Boolean).join(' / ');
  return (
    <div
      className="flex items-center justify-between rounded-lg border bg-card p-4"
      data-testid="mute-row"
    >
      <div className="space-y-0.5">
        <p className="font-medium">{mute.muted_persona_name}</p>
        <p className="text-xs text-muted-foreground">Hidden: {scope || 'nothing'}</p>
      </div>
      <Button
        variant="outline"
        size="sm"
        onClick={() => unmute.mutate(mute.id)}
        disabled={unmute.isPending}
      >
        Unmute
      </Button>
    </div>
  );
}

export function MutesSettingsPage() {
  const { data, isLoading } = useMutes();
  const mutes = data?.results ?? [];
  return (
    <ErrorBoundary>
      <div className="space-y-4">
        <div>
          <h2 className="text-lg font-semibold">Muted</h2>
          <p className="text-sm text-muted-foreground">
            Characters you've quietly filtered from your own feed. They are never told.
          </p>
        </div>
        {isLoading ? (
          <Skeleton className="h-20 w-full" />
        ) : mutes.length === 0 ? (
          <p className="text-sm text-muted-foreground">You haven't muted anyone.</p>
        ) : (
          <div className="space-y-3">
            {mutes.map((mute) => (
              <MuteRow key={mute.id} mute={mute} />
            ))}
          </div>
        )}
      </div>
    </ErrorBoundary>
  );
}

export default MutesSettingsPage;

/**
 * SanctumDashboardPage — landing page for the player's Sanctum surface.
 *
 * Lists every Sanctum the active persona has standing in (owned or woven
 * into) and offers the per-Sanctum actions via SanctumCard. Install-wizard
 * (creating a new Sanctum from scratch) is a deferred follow-up — the
 * backend endpoint for opening an install Project isn't yet built.
 */

import { Skeleton } from '@/components/ui/skeleton';

import { SanctumCard } from '../components/sanctum/SanctumCard';
import { useSanctums } from '../sanctumQueries';

export function SanctumDashboardPage() {
  const { data, isLoading, isError, error } = useSanctums();

  if (isLoading) {
    return (
      <div className="mx-auto max-w-5xl space-y-4 p-6">
        <h1 className="text-2xl font-semibold">My Sanctums</h1>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <Skeleton className="h-48 w-full" />
          <Skeleton className="h-48 w-full" />
        </div>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="mx-auto max-w-5xl space-y-4 p-6">
        <h1 className="text-2xl font-semibold">My Sanctums</h1>
        <p className="text-sm text-destructive">
          {error instanceof Error ? error.message : 'Failed to load Sanctums.'}
        </p>
      </div>
    );
  }

  const sanctums = data ?? [];

  return (
    <div className="mx-auto max-w-5xl space-y-4 p-6">
      <h1 className="text-2xl font-semibold">My Sanctums</h1>
      {sanctums.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          You don't have any Sanctums yet. Open an install Project in a room you own to consecrate
          one.
        </p>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {sanctums.map((sanctum) => (
            <SanctumCard key={sanctum.feature_instance_id} sanctum={sanctum} />
          ))}
        </div>
      )}
    </div>
  );
}

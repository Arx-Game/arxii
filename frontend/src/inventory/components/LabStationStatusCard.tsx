/**
 * LabStationStatusCard — durability readout + repair action for a room's Lab
 * station (#1234), the crafting-station economy's money-sink mechanic.
 *
 * Mounted from `AttachFacetDialog`'s `CraftingQuotePanel`, which already
 * knows the crafter's room's station via `CraftingQuote.station_status`
 * (Task 13). This component takes only the resolved `feature_instance_id`
 * from that quote and re-fetches live status itself (`useLabStationStatus`)
 * rather than rendering the quote's snapshot directly — that keeps the
 * durability bar accurate immediately after a repair, since
 * `useRepairLabStation` invalidates the `["lab-station", featureInstanceId]`
 * cache key but has no way to invalidate the (unrelated) crafting-quote
 * cache key.
 *
 * Scope note: INSTALL is intentionally not wired here. `AttachFacetDialog`'s
 * component tree has no "current room" context (no `roomProfileId` anywhere
 * above it) to drive `useInstallLabStation`, and this codebase has no
 * established "what room am I in" frontend primitive to invent one from
 * cleanly. When there is no station (`featureInstanceId` is null/undefined)
 * this card only informs the player — it does not offer an install action.
 */

import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { useLabStationStatus, useRepairLabStation } from '../hooks/useLabStation';

interface LabStationStatusCardProps {
  /** Resolved from `CraftingQuote.station_status.feature_instance_id`. Null/undefined = no station present. */
  featureInstanceId: number | null | undefined;
}

export function LabStationStatusCard({ featureInstanceId }: LabStationStatusCardProps) {
  const statusQuery = useLabStationStatus(featureInstanceId ?? undefined);
  const repairMutation = useRepairLabStation(featureInstanceId ?? -1);

  if (featureInstanceId == null) {
    return (
      <div
        className="rounded-md border bg-muted/40 px-3 py-2 text-sm text-destructive"
        data-testid="lab-station-status-card"
      >
        No Lab station in this room.
      </div>
    );
  }

  const station = statusQuery.data;
  if (statusQuery.isLoading || !station) {
    return (
      <p className="text-xs text-muted-foreground" data-testid="lab-station-status-card">
        Loading station status…
      </p>
    );
  }

  const { durability, max_durability, level, is_broken } = station;
  const durabilityPct = max_durability > 0 ? (durability / max_durability) * 100 : 0;
  const needsRepair = durability < max_durability;

  function handleRepair() {
    repairMutation.mutate(
      { restore_points: max_durability - durability },
      {
        onSuccess: () => {
          toast.success('Lab station repaired.');
        },
        onError: (err) => {
          toast.error(err instanceof Error ? err.message : 'Failed to repair Lab station.');
        },
      }
    );
  }

  return (
    <div
      className="space-y-1.5 rounded-md border bg-muted/40 px-3 py-2 text-sm"
      data-testid="lab-station-status-card"
    >
      <p className="font-medium">
        Lab station (L{level}) — {durability}/{max_durability}
        {is_broken && <span className="ml-1 text-destructive">(broken)</span>}
      </p>
      <Progress value={durabilityPct} />
      <Button
        size="sm"
        variant="outline"
        onClick={handleRepair}
        disabled={repairMutation.isPending || !needsRepair}
      >
        {repairMutation.isPending ? 'Repairing…' : 'Repair fully'}
      </Button>
    </div>
  );
}

/**
 * BeatList — ordered list of beats for an episode.
 *
 * Fetches beats and aggregate contributions, then renders BeatRow for each.
 */

import { Skeleton } from '@/components/ui/skeleton';
import { useBeatList, useAggregateBeatContributions } from '../queries';
import { useMyPendingTreasuredSignoffs } from '@/boundaries/queries';
import { BeatRow } from './BeatRow';

interface BeatListProps {
  episodeId: number;
  /**
   * Character sheet ID forwarded to BeatRow for the contribute action.
   * Pass story.character_sheet for CHARACTER-scope stories.
   */
  characterSheetId?: number | null;
  /**
   * Roster tenure ID for the viewer's character on this story (#1853) —
   * forwarded to BeatRow so it can render TreasuredSignoffPrompt when a
   * beat has a pending sign-off. Pass story.character_sheet's tenure, same
   * scope rule as characterSheetId.
   */
  tenureId?: number | null;
}

export function BeatList({ episodeId, characterSheetId, tenureId }: BeatListProps) {
  const { data: beatsPage, isLoading: beatsLoading } = useBeatList({ episode: episodeId });
  const beats = beatsPage?.results ?? [];

  // Fetch all contributions for beats in this episode.
  // We get contributions for each beat id present in the list.
  // This is a single query; filter client-side per beat.
  const aggregateBeatIds = beats
    .filter((b) => b.predicate_type === 'aggregate_threshold')
    .map((b) => b.id);

  // Fetch contributions for the first aggregate beat (if any) as a representative
  // query — the BeatRow needs per-beat totals, so we fetch all contributions for
  // each aggregate beat id individually via the episode filter (episode -> all beats
  // contributions). We use a single call filtered by none (episode not a filter param)
  // and aggregate client-side.
  const { data: contribsPage } = useAggregateBeatContributions(
    aggregateBeatIds.length > 0 ? { page_size: 200 } : undefined
  );
  const contributions = contribsPage?.results ?? [];

  // Sum contributions per beat id
  const totalsByBeatId: Record<number, number> = {};
  for (const c of contributions) {
    if (aggregateBeatIds.includes(c.beat)) {
      totalsByBeatId[c.beat] = (totalsByBeatId[c.beat] ?? 0) + c.points;
    }
  }

  const beatIds = beats.map((b) => b.id);
  const { data: pendingSignoffs } = useMyPendingTreasuredSignoffs(tenureId != null ? beatIds : []);
  const pendingByBeatId = new Map(
    (pendingSignoffs ?? []).map((entry) => [entry.beat_id, entry.treasured_subject_ids])
  );

  if (beatsLoading) {
    return (
      <div className="space-y-2">
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} className="h-16 w-full" />
        ))}
      </div>
    );
  }

  if (beats.length === 0) {
    return <p className="text-sm text-muted-foreground">No beats yet for this episode.</p>;
  }

  return (
    <ul className="space-y-2">
      {beats.map((beat) => (
        <BeatRow
          key={beat.id}
          beat={beat}
          aggregateTotal={totalsByBeatId[beat.id] ?? 0}
          characterSheetId={characterSheetId}
          tenureId={tenureId}
          pendingSignoffSubjectIds={pendingByBeatId.get(beat.id)}
        />
      ))}
    </ul>
  );
}

/**
 * BeatTrack — the successes/failures pip rows shared by BeatCard and
 * GroupBeatCard (#3568). Renders nothing when the beat has no track.
 */
import { Pips } from '@/components/ui/pips';

import type { TrackView } from '../types';

export function BeatTrack({ track }: { track: TrackView | null }) {
  if (!track) return null;
  return (
    <div className="flex gap-3" data-testid="beat-track">
      <Pips
        filled={track.successes}
        total={track.needed}
        label="Successes"
        tone="success"
        testId="beat-track-successes"
      />
      <Pips
        filled={track.failures}
        total={track.allowed}
        label="Failures"
        tone="failure"
        testId="beat-track-failures"
      />
    </div>
  );
}

/**
 * StoryLog — vertical timeline of beat completions and episode resolutions.
 *
 * BeatCompletion entries show outcome pill, resolution text, and relative time.
 * EpisodeResolution entries show the episode title and transition info.
 * Staff/Lead GM viewers see internal_description / gm_notes behind a toggle.
 */

import { useState } from 'react';
import { Skeleton } from '@/components/ui/skeleton';
import { formatRelativeTime } from '@/lib/relativeTime';
import { BeatOutcomeBadge } from './BeatOutcomeBadge';
import { useStoryLog } from '../queries';
import type { StoryLogBeatEntry, StoryLogEpisodeEntry, StoryLogEntry } from '../types';

// ---------------------------------------------------------------------------
// Individual entry renderers
// ---------------------------------------------------------------------------

function BeatCompletionEntry({ entry }: { entry: StoryLogBeatEntry }) {
  const [showInternal, setShowInternal] = useState(false);
  const hasInternal = entry.internal_description != null || entry.gm_notes != null;

  const bodyText =
    entry.player_resolution_text ??
    (entry.player_hint && entry.player_hint.trim().length > 0 ? entry.player_hint : null);

  return (
    <div className="relative pl-6">
      {/* Timeline dot */}
      <span className="absolute left-0 top-1 flex h-4 w-4 items-center justify-center rounded-full bg-border ring-2 ring-background" />

      <div className="space-y-1">
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <BeatOutcomeBadge outcome={entry.outcome} />
          <span className="text-xs text-muted-foreground">
            {formatRelativeTime(entry.recorded_at)}
          </span>
        </div>

        {bodyText && <p className="text-sm text-foreground/80">{bodyText}</p>}

        {hasInternal && (
          <button
            onClick={() => setShowInternal((v) => !v)}
            className="text-xs text-muted-foreground underline hover:text-foreground"
          >
            {showInternal ? 'Hide internal notes' : 'Show internal notes'}
          </button>
        )}

        {showInternal && hasInternal && (
          <div className="space-y-1 rounded border bg-muted/50 p-2 text-xs">
            {entry.internal_description && (
              <p>
                <span className="font-medium">Description:</span> {entry.internal_description}
              </p>
            )}
            {entry.gm_notes && (
              <p>
                <span className="font-medium">GM notes:</span> {entry.gm_notes}
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function EpisodeResolutionEntry({ entry }: { entry: StoryLogEpisodeEntry }) {
  const [showInternal, setShowInternal] = useState(false);
  const hasInternal = entry.internal_notes != null;

  return (
    <div className="relative pl-6">
      {/* Timeline dot — distinct color for episode resolutions */}
      <span className="absolute left-0 top-1 flex h-4 w-4 items-center justify-center rounded-full bg-blue-500 ring-2 ring-background" />

      <div className="space-y-1">
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="font-medium">Episode resolved: {entry.episode_title}</span>
          <span className="text-xs text-muted-foreground">
            {formatRelativeTime(entry.resolved_at)}
          </span>
        </div>

        {entry.connection_type && entry.connection_summary && (
          <p className="text-sm text-muted-foreground">
            {entry.connection_type}: {entry.connection_summary}
          </p>
        )}

        {entry.target_episode_title && (
          <p className="text-sm text-muted-foreground">Next: {entry.target_episode_title}</p>
        )}

        {hasInternal && (
          <button
            onClick={() => setShowInternal((v) => !v)}
            className="text-xs text-muted-foreground underline hover:text-foreground"
          >
            {showInternal ? 'Hide internal notes' : 'Show internal notes'}
          </button>
        )}

        {showInternal && entry.internal_notes && (
          <div className="rounded border bg-muted/50 p-2 text-xs">
            <span className="font-medium">Internal notes:</span> {entry.internal_notes}
          </div>
        )}
      </div>
    </div>
  );
}

function LogEntry({ entry }: { entry: StoryLogEntry }) {
  if (entry.entry_type === 'beat_completion') {
    return <BeatCompletionEntry entry={entry} />;
  }
  return <EpisodeResolutionEntry entry={entry} />;
}

// ---------------------------------------------------------------------------
// StoryLog
// ---------------------------------------------------------------------------

interface StoryLogProps {
  storyId: number;
}

export function StoryLog({ storyId }: StoryLogProps) {
  const { data, isLoading } = useStoryLog(storyId);

  if (isLoading) {
    return (
      <div className="space-y-4">
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} className="h-12 w-full" />
        ))}
      </div>
    );
  }

  const entries = data?.entries ?? [];

  if (entries.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        Story log is empty. Beats will appear here as they resolve.
      </p>
    );
  }

  return (
    <div className="relative border-l border-border pl-2">
      <div className="space-y-6">
        {entries.map((entry, idx) => (
          <LogEntry
            key={
              entry.entry_type === 'beat_completion'
                ? `beat-${entry.beat_id}-${idx}`
                : `ep-${entry.episode_id}-${idx}`
            }
            entry={entry}
          />
        ))}
      </div>
    </div>
  );
}

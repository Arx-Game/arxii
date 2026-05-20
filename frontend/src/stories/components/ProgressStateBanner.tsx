/**
 * ProgressStateBanner — Task F1
 *
 * Thin, read-only banner shown in the StoryAuthorPage selected-story pane
 * (under the header, above the Tree/DAG/GM-Notes tabs) so the GM always has
 * at-a-glance context for where the assigned PC/group currently is and
 * whether the story is paused waiting on the GM. This is the "nimble
 * in-session" context surface; the actual run-control actions are F2.
 *
 * DATA SOURCE:
 *   useMyActiveStories() → GET /api/stories/my-active/, keyed by story_id
 *   across the three scope arrays. Each entry now carries the authoritative
 *   `progress_status` (the backbone ProgressStatus pointer state:
 *   active/waiting_for_gm/resting/completed — ledger (e)) alongside the
 *   coarser StoryEpisodeStatus `status` frontier proxy. The banner derives
 *   its treatment from `progress_status` first so a GM-blocked pause
 *   (waiting_for_gm) is distinguished from a deliberate rest; only the
 *   `active` pointer state defers to the `status` proxy (which still adds
 *   the `on_hold` frontier refinement).
 *
 * Thin read-only banner: NO actions. Selects the dashboard entry whose
 * story_id matches and renders scope + current episode + a status chip with
 * distinct treatment for the GM-attention pause vs. an active episode vs. a
 * muted pause. No matching entry → calm "Not yet running" (not an error).
 */

import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import { useMyActiveStories } from '../queries';
import type { AssignableStoryScope, MyActiveStoryEntry, StoryScope } from '../types';
import { ScopeBadge } from './ScopeBadge';

/** ScopeBadge only renders the three assigned scopes (not 'unassigned'). */
function isAssignableScope(scope: StoryScope): scope is AssignableStoryScope {
  return scope === 'character' || scope === 'group' || scope === 'global';
}

// ---------------------------------------------------------------------------
// Status → treatment mapping
//
// The dashboard sends a StoryEpisodeStatus value. We map it to one of three
// author-facing treatments:
//   - 'attention' — story is paused and the GM has the ball (frontier:
//     next episode unauthored). This is the WAITING_FOR_GM / RESTING
//     analogue the author most needs flagged.
//   - 'active'    — an episode is live and can advance now.
//   - 'muted'     — paused but not GM-blocked (scheduled / waiting on beats).
// status_label (the backend's human-readable label) is shown as-is, except
// the attention state which gets explicit "Waiting for GM" copy so the
// author instantly knows the story is parked on them.
// ---------------------------------------------------------------------------

type BannerState = 'attention' | 'active' | 'muted' | 'idle';

const STATUS_TREATMENT: Record<string, Exclude<BannerState, 'idle'>> = {
  on_hold: 'attention',
  ready_to_resolve: 'active',
  ready_to_schedule: 'muted',
  scheduled: 'muted',
  waiting_on_beats: 'muted',
  completed: 'muted',
};

function treatmentFor(status: string): Exclude<BannerState, 'idle'> {
  return STATUS_TREATMENT[status] ?? 'muted';
}

// Authoritative ProgressStatus → treatment. 'active' is intentionally absent:
// an active pointer defers to the StoryEpisodeStatus proxy above (which adds
// the `on_hold` frontier refinement the pointer state alone can't express).
const PROGRESS_STATUS_TREATMENT: Record<string, Exclude<BannerState, 'idle'>> = {
  waiting_for_gm: 'attention',
  resting: 'muted',
  completed: 'muted',
};

function bannerStateFor(entry: MyActiveStoryEntry): Exclude<BannerState, 'idle'> {
  return PROGRESS_STATUS_TREATMENT[entry.progress_status] ?? treatmentFor(entry.status);
}

const STATE_CHIP_CLASSES: Record<Exclude<BannerState, 'idle'>, string> = {
  attention: 'bg-amber-600 text-white border-transparent',
  active: 'bg-green-600 text-white border-transparent',
  muted: 'bg-secondary text-secondary-foreground border-transparent',
};

const STATE_CONTAINER_CLASSES: Record<BannerState, string> = {
  attention: 'border-amber-500/60 bg-amber-500/10',
  active: 'border-green-600/40 bg-green-600/5',
  muted: 'border-border bg-muted/40',
  idle: 'border-dashed border-border bg-muted/20',
};

/**
 * Status copy shown in the chip. The GM-attention pause gets explicit
 * "Waiting for GM" copy; everything else uses the backend's own label.
 */
function statusCopy(entry: MyActiveStoryEntry): string {
  if (entry.progress_status === 'waiting_for_gm') {
    return 'Waiting for GM';
  }
  if (entry.progress_status === 'resting') {
    return 'Resting';
  }
  // 'active'/unknown pointer → keep the proxy behaviour (an `on_hold`
  // frontier still reads as "Waiting for GM").
  if (treatmentFor(entry.status) === 'attention') {
    return 'Waiting for GM';
  }
  return entry.status_label;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface ProgressStateBannerProps {
  storyId: number;
  scope: StoryScope;
}

export function ProgressStateBanner({ storyId, scope }: ProgressStateBannerProps) {
  const { data, isLoading } = useMyActiveStories();

  if (isLoading) {
    return (
      <div
        className="mb-4 h-12 animate-pulse rounded-md border border-border bg-muted/40"
        data-testid="progress-state-loading"
        aria-hidden="true"
      />
    );
  }

  const entry: MyActiveStoryEntry | undefined = data
    ? [...data.character_stories, ...data.group_stories, ...data.global_stories].find(
        (e) => e.story_id === storyId
      )
    : undefined;

  // No active-progress row for this story (UNASSIGNED, not started, or not
  // among the GM's active stories). Calm note — NOT an error.
  if (!entry) {
    return (
      <div
        className={cn(
          'mb-4 flex items-center gap-2 rounded-md border px-3 py-2 text-sm',
          STATE_CONTAINER_CLASSES.idle
        )}
        data-testid="progress-state-banner"
        data-state="idle"
      >
        {isAssignableScope(scope) && <ScopeBadge scope={scope} className="text-xs" />}
        <span className="text-muted-foreground" data-testid="progress-state-idle">
          Not yet running — no active progress for this story.
        </span>
      </div>
    );
  }

  const state: BannerState = bannerStateFor(entry);
  const episodeLabel = entry.current_episode_title ?? 'At frontier';

  return (
    <div
      className={cn(
        'mb-4 flex flex-wrap items-center gap-2 rounded-md border px-3 py-2 text-sm',
        STATE_CONTAINER_CLASSES[state]
      )}
      data-testid="progress-state-banner"
      data-state={state}
    >
      {isAssignableScope(scope) && <ScopeBadge scope={scope} className="text-xs" />}
      <span className="text-muted-foreground">Currently in</span>
      <span
        className={cn('font-medium', state === 'active' && 'text-foreground')}
        data-testid="progress-state-episode"
      >
        {episodeLabel}
      </span>
      <Badge
        className={cn('ml-auto', STATE_CHIP_CLASSES[state])}
        data-testid="progress-state-status"
      >
        {statusCopy(entry)}
      </Badge>
    </div>
  );
}

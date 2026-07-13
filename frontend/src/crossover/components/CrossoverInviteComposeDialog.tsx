/**
 * CrossoverInviteComposeDialog — GM composes a crossover invite (#2075).
 *
 * Form fields: event picker, story picker, optional episode picker, optional message.
 * Placed on StoryDetailPage (and optionally TableDetailPage).
 *
 * The inviting GM is resolved server-side from request.user.gm_profile. If the user
 * lacks a GMProfile, the API returns 403 and the dialog surfaces the error.
 */

import { useState } from 'react';
import { toast } from 'sonner';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { useStoryList } from '@/stories/queries';
import { useEpisodeList } from '@/stories/queries';
import { fetchEvents } from '@/events/queries';
import { useQuery } from '@tanstack/react-query';
import type { EventListItem } from '@/events/types';
import type { StoryList } from '@/stories/types';
import type { EpisodeList } from '@/stories/types';
import { useCreateCrossoverInvite } from '../queries';

// ---------------------------------------------------------------------------
// DRF error shapes
// ---------------------------------------------------------------------------

interface DRFFieldErrors {
  event?: string[];
  to_story?: string[];
  proposed_episode?: string[];
  message?: string[];
  non_field_errors?: string[];
  detail?: string;
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface CrossoverInviteComposeDialogProps {
  /** The current story's ID — excluded from the story picker (can't invite self). */
  currentStoryId?: number;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function CrossoverInviteComposeDialog({
  currentStoryId,
}: CrossoverInviteComposeDialogProps) {
  const [open, setOpen] = useState(false);
  const [eventId, setEventId] = useState<number | null>(null);
  const [toStoryId, setToStoryId] = useState<number | null>(null);
  const [proposedEpisodeId, setProposedEpisodeId] = useState<number | null>(null);
  const [message, setMessage] = useState('');
  const [fieldErrors, setFieldErrors] = useState<DRFFieldErrors>({});

  const createMutation = useCreateCrossoverInvite();

  // Load events for the event picker
  const { data: eventsData } = useQuery({
    queryKey: ['events-for-crossover'],
    queryFn: () => fetchEvents({ page_size: '50' }),
    enabled: open,
  });
  const events = (eventsData?.results ?? []) as EventListItem[];

  // Load stories for the story picker (exclude current story)
  const { data: storiesData } = useStoryList({ page_size: 50 });
  const stories = (storiesData?.results ?? []) as StoryList[];

  // Load episodes for the selected story (episode picker)
  const { data: episodesData } = useEpisodeList(
    toStoryId != null ? { story: toStoryId, page_size: 50 } : undefined
  );
  const episodes = (episodesData?.results ?? []) as EpisodeList[];

  function handleOpenChange(next: boolean) {
    setOpen(next);
    if (next) {
      setEventId(null);
      setToStoryId(null);
      setProposedEpisodeId(null);
      setMessage('');
      setFieldErrors({});
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (eventId == null) return;
    setFieldErrors({});

    createMutation.mutate(
      {
        event: eventId,
        to_story: toStoryId!,
        proposed_episode: proposedEpisodeId ?? undefined,
        message: message.trim() || undefined,
      },
      {
        onSuccess: () => {
          toast.success('Crossover invite sent');
          setOpen(false);
        },
        onError: (err: unknown) => {
          if (err && typeof err === 'object') {
            setFieldErrors(err as DRFFieldErrors);
          } else {
            toast.error('Failed to send crossover invite. Please try again.');
          }
        },
      }
    );
  }

  const nonFieldErrors = fieldErrors.non_field_errors ?? [];
  const detailError = fieldErrors.detail ?? '';

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm" data-testid="crossover-invite-button">
          Invite Story to Crossover
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>Send Crossover Invite</DialogTitle>
            <DialogDescription>
              Invite another story&apos;s Lead GM to co-run a shared event.
            </DialogDescription>
          </DialogHeader>

          {(nonFieldErrors.length > 0 || detailError) && (
            <div className="mt-4 rounded-md bg-destructive/10 px-4 py-3 text-sm text-destructive">
              {detailError && <p>{detailError}</p>}
              {nonFieldErrors.map((msg, i) => (
                <p key={i}>{msg}</p>
              ))}
            </div>
          )}

          <div className="mt-4 grid gap-4">
            {/* Event picker */}
            <div className="space-y-1.5">
              <Label>Event</Label>
              <Select
                value={eventId?.toString() ?? ''}
                onValueChange={(v) => setEventId(Number(v))}
              >
                <SelectTrigger data-testid="crossover-event-select">
                  <SelectValue placeholder="Select a shared event…" />
                </SelectTrigger>
                <SelectContent>
                  {events.map((event) => (
                    <SelectItem key={event.id} value={event.id.toString()}>
                      {event.name}
                      {event.scheduled_real_time &&
                        ` — ${new Date(event.scheduled_real_time).toLocaleDateString()}`}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {fieldErrors.event && (
                <p className="text-xs text-destructive">{fieldErrors.event.join(' ')}</p>
              )}
            </div>

            {/* Story picker */}
            <div className="space-y-1.5">
              <Label>Story to Invite</Label>
              <Select
                value={toStoryId?.toString() ?? ''}
                onValueChange={(v) => {
                  setToStoryId(Number(v));
                  setProposedEpisodeId(null);
                }}
              >
                <SelectTrigger data-testid="crossover-story-select">
                  <SelectValue placeholder="Select a story to invite…" />
                </SelectTrigger>
                <SelectContent>
                  {stories
                    .filter((s) => s.id !== currentStoryId)
                    .map((story) => (
                      <SelectItem key={story.id} value={story.id.toString()}>
                        {story.title}
                      </SelectItem>
                    ))}
                </SelectContent>
              </Select>
              {fieldErrors.to_story && (
                <p className="text-xs text-destructive">{fieldErrors.to_story.join(' ')}</p>
              )}
            </div>

            {/* Optional episode picker */}
            {toStoryId != null && (
              <div className="space-y-1.5">
                <Label>
                  Proposed Episode <span className="text-muted-foreground">(optional)</span>
                </Label>
                <Select
                  value={proposedEpisodeId?.toString() ?? ''}
                  onValueChange={(v) => setProposedEpisodeId(Number(v))}
                >
                  <SelectTrigger data-testid="crossover-episode-select">
                    <SelectValue placeholder="Let the Lead GM pick…" />
                  </SelectTrigger>
                  <SelectContent>
                    {episodes.map((ep) => (
                      <SelectItem key={ep.id} value={ep.id.toString()}>
                        {ep.title ?? `Episode ${ep.order}`}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {fieldErrors.proposed_episode && (
                  <p className="text-xs text-destructive">
                    {fieldErrors.proposed_episode.join(' ')}
                  </p>
                )}
              </div>
            )}

            {/* Optional message */}
            <div className="space-y-1.5">
              <Label>
                Message <span className="text-muted-foreground">(optional)</span>
              </Label>
              <Textarea
                placeholder="A note for the invited GM…"
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                rows={3}
                data-testid="crossover-message-input"
              />
              {fieldErrors.message && (
                <p className="text-xs text-destructive">{fieldErrors.message.join(' ')}</p>
              )}
            </div>
          </div>

          <DialogFooter className="mt-6">
            <Button
              type="button"
              variant="outline"
              onClick={() => setOpen(false)}
              disabled={createMutation.isPending}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={createMutation.isPending || eventId == null || toStoryId == null}
              data-testid="crossover-submit-button"
            >
              {createMutation.isPending ? 'Sending…' : 'Send Invite'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

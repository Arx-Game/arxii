/**
 * AcceptInviteDialog — Lead GM accepts a crossover invite (#2075).
 *
 * Fields: episode picker (required if no proposed_episode, optional otherwise),
 * optional response note. On submit: calls useAcceptCrossoverInvite.
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
import { useEpisodeList } from '@/stories/queries';
import type { EpisodeList } from '@/stories/types';
import { useAcceptCrossoverInvite } from '../queries';
import type { CrossoverInvite } from '../types';

interface AcceptInviteDialogProps {
  invite: CrossoverInvite;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function AcceptInviteDialog({ invite, open, onOpenChange }: AcceptInviteDialogProps) {
  const [acceptedEpisodeId, setAcceptedEpisodeId] = useState<number | null>(
    invite.proposed_episode
  );
  const [responseNote, setResponseNote] = useState('');
  const acceptMutation = useAcceptCrossoverInvite();

  const { data: episodesData } = useEpisodeList({ story: invite.to_story, page_size: 50 });
  const episodes = (episodesData?.results ?? []) as EpisodeList[];

  const hasProposedEpisode = invite.proposed_episode != null;

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (acceptedEpisodeId == null) return;

    acceptMutation.mutate(
      {
        id: invite.id,
        accepted_episode: acceptedEpisodeId,
        response_note: responseNote.trim() || undefined,
      },
      {
        onSuccess: () => {
          toast.success('Crossover invite accepted');
          onOpenChange(false);
        },
        onError: () => {
          toast.error('Failed to accept invite. Please try again.');
        },
      }
    );
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>Accept Crossover Invite</DialogTitle>
            <DialogDescription>
              Select an episode to link to the shared event. The invited story&apos;s Lead GM will
              be enrolled as a scene GM.
            </DialogDescription>
          </DialogHeader>

          <div className="mt-4 grid gap-4">
            <div className="space-y-1.5">
              <Label>
                Episode {!hasProposedEpisode && <span className="text-destructive">*</span>}
              </Label>
              <Select
                value={acceptedEpisodeId?.toString() ?? ''}
                onValueChange={(v) => setAcceptedEpisodeId(Number(v))}
              >
                <SelectTrigger data-testid="accept-episode-select">
                  <SelectValue placeholder="Select an episode to link…" />
                </SelectTrigger>
                <SelectContent>
                  {episodes.map((ep) => (
                    <SelectItem key={ep.id} value={ep.id.toString()}>
                      {ep.name ?? `Episode ${ep.order}`}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {hasProposedEpisode && (
                <p className="text-xs text-muted-foreground">
                  The inviter proposed an episode. You can keep it or pick another.
                </p>
              )}
            </div>

            <div className="space-y-1.5">
              <Label>
                Response Note <span className="text-muted-foreground">(optional)</span>
              </Label>
              <Textarea
                placeholder="A note for the inviting GM…"
                value={responseNote}
                onChange={(e) => setResponseNote(e.target.value)}
                rows={3}
                data-testid="accept-response-note"
              />
            </div>
          </div>

          <DialogFooter className="mt-6">
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={acceptMutation.isPending}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={acceptMutation.isPending || acceptedEpisodeId == null}
              data-testid="accept-submit-button"
            >
              {acceptMutation.isPending ? 'Accepting…' : 'Accept Invite'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

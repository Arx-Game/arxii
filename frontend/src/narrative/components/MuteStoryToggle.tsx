/**
 * MuteStoryToggle — bell icon button that mutes / unmutes real-time story updates.
 *
 * Two states:
 *  - Not muted: Bell icon, click calls muteStory(storyId).
 *  - Muted: BellOff icon, click calls unmuteStory(muteId).
 *
 * The mute lookup is derived by finding the matching mute in useStoryMutes()
 * for this storyId. The backend ensures at most one mute per (account, story).
 */

import { Bell, BellOff } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useStoryMutes, useMuteStory, useUnmuteStory } from '../queries';

interface MuteStoryToggleProps {
  storyId: number;
}

export function MuteStoryToggle({ storyId }: MuteStoryToggleProps) {
  const { data: mutesData } = useStoryMutes();
  const muteStory = useMuteStory();
  const unmuteStory = useUnmuteStory();

  const existingMute = mutesData?.results.find((m) => m.story === storyId);
  const isMuted = existingMute != null;

  const handleClick = () => {
    if (isMuted && existingMute != null) {
      unmuteStory.mutate(existingMute.id);
    } else {
      muteStory.mutate({ story: storyId });
    }
  };

  const isPending = muteStory.isPending || unmuteStory.isPending;

  const tooltip = isMuted
    ? 'Unmute: resume real-time updates from this story'
    : "Mute real-time updates from this story (you'll still see it in your dashboard)";

  return (
    <Button
      variant="ghost"
      size="sm"
      onClick={handleClick}
      disabled={isPending}
      aria-label={isMuted ? 'Unmute story updates' : 'Mute story updates'}
      title={tooltip}
      data-testid="mute-story-toggle"
      data-muted={isMuted ? 'true' : 'false'}
    >
      {isMuted ? (
        <BellOff className="h-4 w-4 text-muted-foreground" />
      ) : (
        <Bell className="h-4 w-4" />
      )}
    </Button>
  );
}

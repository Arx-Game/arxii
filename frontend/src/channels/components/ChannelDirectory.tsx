import { Button } from '@/components/ui/button';
import { useJoinChannel } from '../queries';
import type { Channel } from '../types';

/** Channels the account can reach but has not joined. */
export function ChannelDirectory({ channels }: { channels: Channel[] }) {
  const join = useJoinChannel();
  if (channels.length === 0) return null;
  return (
    <section className="space-y-1" aria-label="Join a channel">
      <h3 className="px-1 text-xs font-semibold text-muted-foreground">Join a channel</h3>
      <ul className="space-y-1">
        {channels.map((channel) => (
          <li key={channel.id} className="flex items-center justify-between gap-2 px-1 text-sm">
            <span className="truncate">{channel.name}</span>
            <Button
              variant="outline"
              size="sm"
              className="h-7"
              disabled={join.isPending}
              onClick={() => join.mutate(channel.id)}
            >
              Join
            </Button>
          </li>
        ))}
      </ul>
    </section>
  );
}

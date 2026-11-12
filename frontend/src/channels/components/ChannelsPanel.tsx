import { useChannelsQuery, useReorderSubscriptions } from '../queries';
import type { Channel, JoinedChannel } from '../types';
import { ChannelDirectory } from './ChannelDirectory';
import { ChannelLane } from './ChannelLane';

function isJoined(channel: Channel): channel is JoinedChannel {
  return channel.subscription !== null;
}

function byLaneOrder(a: JoinedChannel, b: JoinedChannel): number {
  const order = (a.subscription.sort_order ?? 0) - (b.subscription.sort_order ?? 0);
  return order !== 0 ? order : a.name.localeCompare(b.name);
}

/**
 * The joined channels as lanes in the player's order, then the ones to join.
 * `active` says whether the panel is on screen; only then do open lanes fetch
 * and mark themselves read. `poll` makes the list and open lanes refetch on an
 * interval, for a page with no game socket to push to it.
 */
export function ChannelsPanel({ active, poll = false }: { active: boolean; poll?: boolean }) {
  const { data: channels } = useChannelsQuery(poll);
  const reorder = useReorderSubscriptions();
  const all = channels ?? [];
  const lanes = all.filter(isJoined).sort(byLaneOrder);
  const unjoined = all.filter((channel) => !isJoined(channel));

  const move = (index: number, direction: -1 | 1) => {
    const ordered = lanes.map((lane) => lane.subscription);
    const target = index + direction;
    if (target < 0 || target >= ordered.length) return;
    [ordered[index], ordered[target]] = [ordered[target], ordered[index]];
    reorder.mutate(ordered);
  };

  return (
    <div className="space-y-2 p-2">
      {lanes.map((channel, index) => (
        <ChannelLane
          key={channel.id}
          channel={channel}
          active={active}
          poll={poll}
          canMoveUp={index > 0 && !reorder.isPending}
          canMoveDown={index < lanes.length - 1 && !reorder.isPending}
          onMove={(direction) => move(index, direction)}
        />
      ))}
      <ChannelDirectory channels={unjoined} />
    </div>
  );
}

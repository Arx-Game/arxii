import { useMemo } from 'react';
import { useQueries } from '@tanstack/react-query';
import type { FeedNote } from '@/hooks/types';
import { fetchChannelMessages } from './api';
import { channelKeys, useChannelsQuery } from './queries';
import type { Channel, ChannelMessagePage, JoinedChannel } from './types';

/** A channel the player is in and has not muted: the only ones with lines in the feed. */
export function isFeedChannel(channel: Channel): channel is JoinedChannel {
  return channel.subscription !== null && !channel.subscription.muted;
}

/**
 * One channel's cached history (newest first) as feed notes, oldest first. Each
 * run of consecutive hidden rows (a blocked author's lines) folds into one
 * divider note, the way a lane folds them.
 */
export function channelNotes(
  channel: Channel,
  newestFirst: ChannelMessagePage['results']
): FeedNote[] {
  const notes: FeedNote[] = [];
  for (const message of [...newestFirst].reverse()) {
    const meta = {
      id: channel.id,
      name: channel.name,
      messageId: message.id,
      speaker: message.speaker,
      hiddenCount: 0,
    };
    const last = notes[notes.length - 1];
    if (message.is_hidden) {
      if (last?.channel?.hiddenCount) last.channel.hiddenCount += 1;
      else {
        notes.push({
          id: `channel:${message.id}`,
          kind: 'channel',
          content: '',
          timestamp: message.created_at,
          channel: { ...meta, speaker: '', hiddenCount: 1 },
        });
      }
      continue;
    }
    notes.push({
      id: `channel:${message.id}`,
      kind: 'channel',
      content: message.body,
      timestamp: message.created_at,
      channel: meta,
    });
  }
  return notes;
}

/**
 * Every channel line the feed shows (#3299): the cached history of each joined,
 * unmuted channel, read from the same query caches the socket handler writes
 * and the /channels lanes read. `enabled` false (the sidebar holds the lines)
 * fetches nothing and returns no notes. Never carries an account.
 */
export function useChannelFeedNotes(enabled: boolean): FeedNote[] {
  const { data } = useChannelsQuery();
  const channels = useMemo(
    () => (enabled ? (data ?? []).filter(isFeedChannel) : []),
    [enabled, data]
  );
  const pages = useQueries({
    queries: channels.map((channel) => ({
      queryKey: channelKeys.messages(channel.id),
      queryFn: () => fetchChannelMessages(channel.id),
    })),
    combine: (results) => results.map((result) => result.data),
  });
  return useMemo(
    () => channels.flatMap((channel, index) => channelNotes(channel, pages[index]?.results ?? [])),
    [channels, pages]
  );
}

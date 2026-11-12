import { useEffect } from 'react';
import { useMutation, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { useAccount } from '@/store/hooks';
import {
  fetchChannelIdentities,
  fetchChannelMessages,
  fetchChannels,
  joinChannel,
  leaveChannel,
  markChannelRead,
  postChannelMessage,
  updateSubscription,
} from './api';
import type {
  Channel,
  ChannelMessage,
  ChannelMessagePage,
  ChannelSubscription,
  ChannelSubscriptionPatch,
} from './types';

export const channelKeys = {
  all: ['channels'] as const,
  list: () => [...channelKeys.all, 'list'] as const,
  messages: (channelId: number) => [...channelKeys.all, 'messages', channelId] as const,
  identities: (channelId: number) => [...channelKeys.all, 'identities', channelId] as const,
};

/**
 * Lanes on screen right now (panel shown, lane expanded), counted per channel
 * because the sidebar and the /channels page can both show one. The socket
 * handler reads this to skip the unread bump and the toast for a lane the
 * player is already reading.
 */
const openLanes = new Map<number, number>();

export function isChannelLaneOpen(channelId: number): boolean {
  return (openLanes.get(channelId) ?? 0) > 0;
}

/** Registers a lane as open while `open` is true. */
export function useOpenLaneRegistration(channelId: number, open: boolean): void {
  useEffect(() => {
    if (!open) return;
    openLanes.set(channelId, (openLanes.get(channelId) ?? 0) + 1);
    return () => {
      const next = (openLanes.get(channelId) ?? 1) - 1;
      if (next > 0) openLanes.set(channelId, next);
      else openLanes.delete(channelId);
    };
  }, [channelId, open]);
}

/** Adds a message to a channel's cached history if its id is not already there. */
export function addMessageToCache(client: QueryClient, message: ChannelMessage): boolean {
  let added = false;
  client.setQueryData<ChannelMessagePage>(channelKeys.messages(message.channel), (page) => {
    if (!page || page.results.some((row) => row.id === message.id)) return page;
    added = true;
    return { ...page, count: page.count + 1, results: [message, ...page.results] };
  });
  return added;
}

/** Replaces one channel's subscription in the cached channel list. */
export function patchCachedSubscription(
  client: QueryClient,
  channelId: number,
  update: (subscription: ChannelSubscription) => ChannelSubscription
): void {
  client.setQueryData<Channel[]>(channelKeys.list(), (channels) =>
    channels?.map((channel) =>
      channel.id === channelId && channel.subscription
        ? { ...channel, subscription: update(channel.subscription) }
        : channel
    )
  );
}

/** Unread total for the sidebar badge: unmuted subscriptions not set to Nothing. */
export function channelUnreadTotal(channels: Channel[] | undefined): number {
  let total = 0;
  for (const channel of channels ?? []) {
    const sub = channel.subscription;
    if (!sub || sub.muted || sub.notification_level === 'none') continue;
    total += sub.unread_count;
  }
  return total;
}

export function useChannelsQuery() {
  const account = useAccount();
  return useQuery({
    queryKey: channelKeys.list(),
    queryFn: fetchChannels,
    enabled: !!account,
  });
}

export function useChannelUnreadTotal(): number {
  const { data } = useChannelsQuery();
  return channelUnreadTotal(data);
}

export function useChannelMessagesQuery(channelId: number, enabled: boolean) {
  return useQuery({
    queryKey: channelKeys.messages(channelId),
    queryFn: () => fetchChannelMessages(channelId),
    enabled,
  });
}

export function useChannelIdentitiesQuery(channelId: number, enabled: boolean) {
  return useQuery({
    queryKey: channelKeys.identities(channelId),
    queryFn: () => fetchChannelIdentities(channelId),
    enabled,
  });
}

function showError(error: Error): void {
  toast.error(error.message);
}

export function usePostChannelMessage(channelId: number) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: string) => postChannelMessage(channelId, body),
    onSuccess: (message) => {
      addMessageToCache(client, message);
    },
    onError: showError,
  });
}

export function useJoinChannel() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (channelId: number) => joinChannel(channelId),
    onSuccess: () => client.invalidateQueries({ queryKey: channelKeys.list() }),
    onError: showError,
  });
}

export function useLeaveChannel() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (subscriptionId: number) => leaveChannel(subscriptionId),
    onSuccess: () => client.invalidateQueries({ queryKey: channelKeys.list() }),
    onError: showError,
  });
}

export function useUpdateSubscription(channelId: number) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, patch }: { id: number; patch: ChannelSubscriptionPatch }) =>
      updateSubscription(id, patch),
    onSuccess: (subscription) => patchCachedSubscription(client, channelId, () => subscription),
    onError: showError,
  });
}

/** Renumbers `sort_order` to match `ordered`, patching only the rows that moved. */
export function useReorderSubscriptions() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (ordered: ChannelSubscription[]) => {
      await Promise.all(
        ordered.map((sub, index) =>
          sub.sort_order === index ? null : updateSubscription(sub.id, { sort_order: index })
        )
      );
    },
    onSettled: () => client.invalidateQueries({ queryKey: channelKeys.list() }),
    onError: showError,
  });
}

export function useMarkChannelRead(channelId: number) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (subscriptionId: number) => markChannelRead(subscriptionId),
    onSuccess: (subscription) => patchCachedSubscription(client, channelId, () => subscription),
  });
}

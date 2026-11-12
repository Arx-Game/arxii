import { toast } from 'sonner';
import type { ChannelMessagePayload } from './types';
import { addMessageToCache, isChannelLaneOpen, patchCachedSubscription } from '@/channels/queries';
import { queryClient } from '@/queryClient';

/**
 * Message ids already handled. The server pushes the same message to every web
 * session on the account (one socket per open character), so the first socket
 * to deliver it wins and the rest are ignored. Bounded so a long session does
 * not grow it forever.
 */
const seenMessageIds = new Set<number>();
const SEEN_LIMIT = 500;

function remember(messageId: number): boolean {
  if (seenMessageIds.has(messageId)) return false;
  seenMessageIds.add(messageId);
  if (seenMessageIds.size > SEEN_LIMIT) {
    const oldest = seenMessageIds.values().next().value;
    if (oldest !== undefined) seenMessageIds.delete(oldest);
  }
  return true;
}

/** Test seam: forget every handled message id. */
export function resetChannelMessageDedupe(): void {
  seenMessageIds.clear();
}

function isValid(payload: ChannelMessagePayload | undefined): payload is ChannelMessagePayload {
  return (
    !!payload &&
    Number.isInteger(payload.message_id) &&
    Number.isInteger(payload.channel_id) &&
    typeof payload.body === 'string' &&
    typeof payload.speaker === 'string'
  );
}

/**
 * A channel message arrived live (#3299). It never enters the IC feed: it goes
 * into that channel's cached history only. Own messages and lanes the player
 * is already reading change nothing else; otherwise `badge` bumps the unread
 * count and `all` also toasts. `none` stays silent.
 */
export function handleChannelMessagePayload(
  payload: ChannelMessagePayload | undefined
): false | undefined {
  if (!isValid(payload)) return false;
  if (!remember(payload.message_id)) return undefined;

  addMessageToCache(queryClient, {
    id: payload.message_id,
    channel: payload.channel_id,
    speaker: payload.speaker,
    body: payload.body,
    is_hidden: false,
    is_own: payload.is_own,
    created_at: payload.created_at,
  });

  if (payload.is_own || payload.notification_level === 'none') return undefined;
  if (isChannelLaneOpen(payload.channel_id)) return undefined;

  patchCachedSubscription(queryClient, payload.channel_id, (sub) => ({
    ...sub,
    unread_count: sub.unread_count + 1,
  }));
  if (payload.notification_level === 'all') {
    toast(`${payload.channel_name} - ${payload.speaker}: ${payload.body}`);
  }
  return undefined;
}

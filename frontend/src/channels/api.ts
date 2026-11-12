import { apiFetch } from '@/evennia_replacements/api';
import type {
  Channel,
  ChannelIdentity,
  ChannelMessage,
  ChannelMessagePage,
  ChannelSubscription,
  ChannelSubscriptionPatch,
} from './types';

const BASE = '/api/channels';

/** The server's player-facing reason from a 400 body (`{detail}` or `{field: msg | [msg]}`). */
async function errorMessage(res: Response, fallback: string): Promise<string> {
  try {
    const body: unknown = await res.json();
    if (body && typeof body === 'object') {
      for (const value of Object.values(body as Record<string, unknown>)) {
        if (typeof value === 'string') return value;
        if (Array.isArray(value) && typeof value[0] === 'string') return value[0];
      }
    }
  } catch {
    // Not JSON: fall through to the fallback.
  }
  return fallback;
}

async function ensureOk(res: Response, fallback: string): Promise<Response> {
  if (!res.ok) throw new Error(await errorMessage(res, fallback));
  return res;
}

/** Every channel the account can reach, each with its own subscription or null. */
export async function fetchChannels(): Promise<Channel[]> {
  const res = await ensureOk(await apiFetch(`${BASE}/channels/`), 'Failed to load channels');
  return res.json();
}

export async function fetchChannelIdentities(channelId: number): Promise<ChannelIdentity[]> {
  const res = await ensureOk(
    await apiFetch(`${BASE}/channels/${channelId}/identities/`),
    'Failed to load identities'
  );
  return res.json();
}

/** The newest page of a channel's history (newest first). */
export async function fetchChannelMessages(channelId: number): Promise<ChannelMessagePage> {
  const res = await ensureOk(
    await apiFetch(`${BASE}/messages/?channel=${channelId}`),
    'Failed to load messages'
  );
  return res.json();
}

export async function postChannelMessage(channelId: number, body: string): Promise<ChannelMessage> {
  const res = await ensureOk(
    await apiFetch(`${BASE}/messages/`, {
      method: 'POST',
      body: JSON.stringify({ channel: channelId, body }),
    }),
    'Failed to send'
  );
  return res.json();
}

export async function joinChannel(channelId: number): Promise<ChannelSubscription> {
  const res = await ensureOk(
    await apiFetch(`${BASE}/subscriptions/`, {
      method: 'POST',
      body: JSON.stringify({ channel: channelId }),
    }),
    'Failed to join'
  );
  return res.json();
}

export async function updateSubscription(
  subscriptionId: number,
  patch: ChannelSubscriptionPatch
): Promise<ChannelSubscription> {
  const res = await ensureOk(
    await apiFetch(`${BASE}/subscriptions/${subscriptionId}/`, {
      method: 'PATCH',
      body: JSON.stringify(patch),
    }),
    'Failed to save'
  );
  return res.json();
}

export async function leaveChannel(subscriptionId: number): Promise<void> {
  await ensureOk(
    await apiFetch(`${BASE}/subscriptions/${subscriptionId}/`, { method: 'DELETE' }),
    'Failed to leave'
  );
}

export async function markChannelRead(subscriptionId: number): Promise<ChannelSubscription> {
  const res = await ensureOk(
    await apiFetch(`${BASE}/subscriptions/${subscriptionId}/mark-read/`, { method: 'POST' }),
    'Failed to mark read'
  );
  return res.json();
}

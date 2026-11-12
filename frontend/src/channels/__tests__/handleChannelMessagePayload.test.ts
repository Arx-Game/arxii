import { beforeEach, describe, expect, it, vi } from 'vitest';
import { toast } from 'sonner';
import {
  handleChannelMessagePayload,
  resetChannelMessageDedupe,
} from '@/hooks/handleChannelMessagePayload';
import { channelKeys } from '@/channels/queries';
import type { Channel, ChannelMessagePage } from '@/channels/types';
import type { ChannelMessagePayload } from '@/hooks/types';
import { queryClient } from '@/queryClient';

vi.mock('sonner', () => ({
  toast: Object.assign(vi.fn(), { error: vi.fn(), success: vi.fn() }),
}));

const CHANNEL_ID = 3;

function seed(): void {
  const channel: Channel = {
    id: CHANNEL_ID,
    name: 'Public',
    description: '',
    kind: 'public',
    subscription: {
      id: 9,
      channel: CHANNEL_ID,
      display_tenure: 1,
      display_label: 'Ariel',
      muted: false,
      collapsed: false,
      notification_level: 'all',
      sort_order: 0,
      unread_count: 0,
    },
  };
  queryClient.setQueryData<Channel[]>(channelKeys.list(), [channel]);
  queryClient.setQueryData<ChannelMessagePage>(channelKeys.messages(CHANNEL_ID), {
    count: 0,
    results: [],
  });
}

function payload(overrides: Partial<ChannelMessagePayload> = {}): ChannelMessagePayload {
  return {
    message_id: 100,
    channel_id: CHANNEL_ID,
    channel_name: 'Public',
    speaker: '2nd player of Ariel',
    body: 'hello',
    created_at: '2026-11-12T00:00:00Z',
    is_own: false,
    notification_level: 'all',
    ...overrides,
  };
}

const unread = () =>
  queryClient.getQueryData<Channel[]>(channelKeys.list())?.[0].subscription?.unread_count;
const messages = () =>
  queryClient.getQueryData<ChannelMessagePage>(channelKeys.messages(CHANNEL_ID))?.results ?? [];

describe('handleChannelMessagePayload', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    queryClient.clear();
    resetChannelMessageDedupe();
    seed();
  });

  it('handles a message id once, however many sockets deliver it', () => {
    handleChannelMessagePayload(payload());
    handleChannelMessagePayload(payload());
    expect(messages()).toHaveLength(1);
    expect(unread()).toBe(1);
    expect(toast).toHaveBeenCalledTimes(1);
  });

  it('adds an own message without a bump or a toast', () => {
    handleChannelMessagePayload(payload({ is_own: true }));
    expect(messages()).toHaveLength(1);
    expect(unread()).toBe(0);
    expect(toast).not.toHaveBeenCalled();
  });

  it('badge bumps without a toast; none does neither', () => {
    handleChannelMessagePayload(payload({ message_id: 1, notification_level: 'badge' }));
    expect(unread()).toBe(1);
    expect(toast).not.toHaveBeenCalled();
    handleChannelMessagePayload(payload({ message_id: 2, notification_level: 'none' }));
    expect(unread()).toBe(1);
    expect(toast).not.toHaveBeenCalled();
    expect(messages()).toHaveLength(2);
  });

  it('refuses a malformed frame', () => {
    expect(handleChannelMessagePayload(undefined)).toBe(false);
  });
});

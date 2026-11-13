import { beforeEach, describe, expect, it, vi } from 'vitest';
import { toast } from 'sonner';
import { renderHook } from '@testing-library/react';
import {
  handleChannelMessagePayload,
  handleChannelMessageRemovedPayload,
  resetChannelMessageDedupe,
} from '@/hooks/handleChannelMessagePayload';
import { channelKeys, useOpenLaneRegistration } from '@/channels/queries';
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

  it('a lane on screen gets the row but no bump and no toast', () => {
    const lane = renderHook(() => useOpenLaneRegistration(CHANNEL_ID, true));
    handleChannelMessagePayload(payload());
    lane.unmount();
    expect(messages()).toHaveLength(1);
    expect(unread()).toBe(0);
    expect(toast).not.toHaveBeenCalled();
  });

  it('clips a long body in the toast', () => {
    handleChannelMessagePayload(payload({ body: 'x'.repeat(400) }));
    const text = vi.mocked(toast).mock.calls[0][0] as string;
    expect(text.length).toBeLessThan(200);
  });

  it('channel_message_removed drops the row', () => {
    handleChannelMessagePayload(payload({ message_id: 7 }));
    handleChannelMessagePayload(payload({ message_id: 8 }));
    handleChannelMessageRemovedPayload({ message_id: 7, channel_id: CHANNEL_ID });
    expect(messages().map((row) => row.id)).toEqual([8]);
  });

  it('refuses a malformed frame', () => {
    expect(handleChannelMessagePayload(undefined)).toBe(false);
  });
});

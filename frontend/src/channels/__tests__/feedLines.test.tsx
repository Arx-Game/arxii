/** Channel lines in the feed (#3299): derived from the channel query caches. */
import { renderHook } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { useChannelFeedNotes } from '../feedLines';
import { channelKeys } from '../queries';
import type { Channel, ChannelMessage, ChannelMessagePage } from '../types';

vi.mock('@/store/hooks', () => ({
  useAccount: () => ({ id: 1, is_staff: false }),
  useAppSelector: () => false,
}));
vi.mock('@/evennia_replacements/api', () => ({
  apiFetch: vi.fn(async () => new Response('[]', { status: 200 })),
}));

function channel(id: number, name: string, muted = false): Channel {
  return {
    id,
    name,
    description: '',
    kind: 'public',
    subscription: {
      id: id * 10,
      channel: id,
      display_tenure: 1,
      display_label: 'Ariel',
      muted,
      collapsed: false,
      notification_level: 'badge',
      sort_order: id,
      unread_count: 0,
    },
  };
}

function message(id: number, channelId: number, overrides: Partial<ChannelMessage> = {}) {
  return {
    id,
    channel: channelId,
    speaker: 'Ariel',
    body: `line ${id}`,
    is_hidden: false,
    is_own: false,
    created_at: `2026-11-12T00:00:0${id}Z`,
    ...overrides,
  } satisfies ChannelMessage;
}

function setup(enabled: boolean) {
  const client = new QueryClient({
    defaultOptions: { queries: { staleTime: Infinity, retry: false } },
  });
  client.setQueryData<Channel[]>(channelKeys.list(), [
    channel(1, 'Public'),
    channel(2, 'Guild', true),
  ]);
  const hidden = { is_hidden: true, speaker: '', body: '' };
  const history = (newestFirst: ChannelMessage[]): ChannelMessagePage => ({
    count: newestFirst.length,
    results: newestFirst,
  });
  client.setQueryData(
    channelKeys.messages(1),
    history([message(4, 1), message(3, 1, hidden), message(2, 1, hidden), message(1, 1)])
  );
  client.setQueryData(channelKeys.messages(2), history([message(5, 2)]));
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return renderHook(() => useChannelFeedNotes(enabled), { wrapper });
}

describe('useChannelFeedNotes', () => {
  it('turns cached lines into channel notes, oldest first, folding hidden runs and skipping muted channels', () => {
    const { result } = setup(true);
    expect(
      result.current.map((note) => [note.kind, note.channel?.name, note.channel?.hiddenCount])
    ).toEqual([
      ['channel', 'Public', 0],
      ['channel', 'Public', 2],
      ['channel', 'Public', 0],
    ]);
    expect(result.current.map((note) => note.content)).toEqual(['line 1', '', 'line 4']);
  });

  it('gives no lines while the sidebar holds them', () => {
    const { result } = setup(false);
    expect(result.current).toEqual([]);
  });
});

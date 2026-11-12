/** ChannelsPanel (#3299): lanes from the cached channel list; the network is stubbed. */
import { act, fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi } from 'vitest';

import { ChannelsPanel } from '../components/ChannelsPanel';
import { addMessageToCache, channelKeys } from '../queries';
import type { Channel, ChannelMessage, ChannelMessagePage, ChannelSubscription } from '../types';

const account = vi.hoisted(() => ({ current: null as { is_staff: boolean } | null }));
vi.mock('@/store/hooks', () => ({
  useAccount: () => account.current,
  useAppSelector: () => false,
}));
vi.mock('@/evennia_replacements/api', () => ({
  apiFetch: vi.fn(async () => new Response('[]', { status: 200 })),
}));

function channel(subscription: Partial<ChannelSubscription>): Channel {
  return {
    id: 3,
    name: 'Public',
    description: '',
    kind: 'public',
    subscription: {
      id: 9,
      channel: 3,
      display_tenure: 1,
      display_label: 'Ariel',
      muted: false,
      collapsed: false,
      notification_level: 'all',
      sort_order: 0,
      unread_count: 0,
      ...subscription,
    },
  };
}

function message(id: number, overrides: Partial<ChannelMessage> = {}): ChannelMessage {
  return {
    id,
    channel: 3,
    speaker: 'Ariel',
    body: `line ${id}`,
    is_hidden: false,
    is_own: false,
    created_at: '2026-11-12T00:00:00Z',
    ...overrides,
  };
}

function renderPanel(channels: Channel[], newestFirst: ChannelMessage[] = []) {
  const client = new QueryClient({
    defaultOptions: { queries: { staleTime: Infinity, retry: false } },
  });
  client.setQueryData<Channel[]>(channelKeys.list(), channels);
  client.setQueryData<ChannelMessagePage>(channelKeys.messages(3), {
    count: newestFirst.length,
    results: newestFirst,
  });
  const view = render(
    <QueryClientProvider client={client}>
      <ChannelsPanel active />
    </QueryClientProvider>
  );
  return { ...view, client };
}

describe('ChannelsPanel', () => {
  it('folds a run of hidden rows into one "N hidden" divider', () => {
    const hidden = { is_hidden: true, speaker: '', body: '' };
    renderPanel([channel({})], [message(4), message(3, hidden), message(2, hidden), message(1)]);
    expect(screen.getAllByTestId('hidden-divider')).toHaveLength(1);
    expect(screen.getByText('2 hidden')).toBeInTheDocument();
    expect(screen.getByText('line 1')).toBeInTheDocument();
    expect(screen.getByText('line 4')).toBeInTheDocument();
  });

  it('a collapsed lane shows its header but no messages', () => {
    renderPanel([channel({ collapsed: true })], [message(1)]);
    expect(screen.getByRole('button', { name: 'Public' })).toBeInTheDocument();
    expect(screen.queryByTestId('channel-messages')).not.toBeInTheDocument();
    expect(screen.queryByText('line 1')).not.toBeInTheDocument();
  });

  it('a lane with no identity shows the identity picker instead of the composer', () => {
    renderPanel([channel({ display_tenure: null, display_label: null })]);
    expect(screen.getByRole('combobox', { name: 'Speak as' })).toBeInTheDocument();
    expect(screen.queryByRole('textbox', { name: 'Message' })).not.toBeInTheDocument();
  });

  it('shows Delete and Ban on messages to staff only', () => {
    account.current = null;
    const { unmount } = renderPanel([channel({})], [message(1)]);
    expect(screen.queryByRole('button', { name: 'Delete' })).not.toBeInTheDocument();
    unmount();
    account.current = { is_staff: true };
    renderPanel([channel({})], [message(1)]);
    expect(screen.getByRole('button', { name: 'Delete' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Ban' })).toBeInTheDocument();
    account.current = null;
  });

  it('opens on the newest message and follows only a reader at the bottom', async () => {
    // jsdom has no layout: give every list a fixed content and viewport height.
    const proto = HTMLOListElement.prototype;
    Object.defineProperty(proto, 'scrollHeight', { configurable: true, get: () => 1000 });
    Object.defineProperty(proto, 'clientHeight', { configurable: true, get: () => 200 });
    try {
      const { client } = renderPanel([channel({})], [message(2), message(1)]);
      const list = screen.getByTestId('channel-messages');
      expect(list.scrollTop).toBe(1000);

      // Scrolled up to read: a new message does not pull the reader down.
      list.scrollTop = 100;
      fireEvent.scroll(list);
      act(() => {
        addMessageToCache(client, message(3));
      });
      expect(await screen.findByText('line 3')).toBeInTheDocument();
      expect(list.scrollTop).toBe(100);

      // Back at the bottom: the next message is followed.
      list.scrollTop = 800;
      fireEvent.scroll(list);
      act(() => {
        addMessageToCache(client, message(4));
      });
      expect(await screen.findByText('line 4')).toBeInTheDocument();
      expect(list.scrollTop).toBe(1000);
    } finally {
      delete (proto as unknown as Record<string, unknown>).scrollHeight;
      delete (proto as unknown as Record<string, unknown>).clientHeight;
    }
  });
});

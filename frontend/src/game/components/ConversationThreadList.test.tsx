import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ConversationThreadList } from './ConversationThreadList';
import * as playQueries from '../playQueries';
import type { ThreadSummary } from '../playTypes';

function renderWithClient(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

function thread(overrides: Partial<ThreadSummary> = {}): ThreadSummary {
  return {
    id: 'thread-1',
    conversation: { kind: 'room', key: 'scene:412' },
    root: { id: '11', timestamp: '2026-06-14T10:00:00Z' },
    firstVisible: { id: '11', timestamp: '2026-06-14T10:00:00Z' },
    latestVisible: { id: '18', timestamp: '2026-06-14T10:40:00Z' },
    opening: 'You came anyway. I did wonder.',
    visiblePoseCount: 4,
    unread: 2,
    directUnread: 0,
    ...overrides,
  };
}

function page(results: ThreadSummary[], after: string | null = null) {
  return { results, before: null, after, snapshot: '2026-06-14T12:00:00Z' };
}

describe('ConversationThreadList', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders a row per thread with its opening line, pose count and unread pill', async () => {
    vi.spyOn(playQueries, 'fetchPlayThreads').mockResolvedValue(
      page([thread(), thread({ id: 'thread-2', opening: 'Keep your voice down.', unread: 0 })])
    );
    renderWithClient(
      <ConversationThreadList conversationKey="scene:412" onOpenThread={() => {}} />
    );
    const firstRow = await screen.findByRole('button', {
      name: /You came anyway\. I did wonder\./,
    });
    expect(firstRow).toBeInTheDocument();
    expect(within(firstRow).getByText(/4 poses/)).toBeInTheDocument();
    expect(within(firstRow).getByText('2')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Keep your voice down\./ })).toBeInTheDocument();
  });

  it('asks the server only for the conversation it was given', async () => {
    const fetchThreads = vi
      .spyOn(playQueries, 'fetchPlayThreads')
      .mockResolvedValue(page([thread()]));
    renderWithClient(
      <ConversationThreadList conversationKey="whisper:3,9" onOpenThread={() => {}} />
    );
    await waitFor(() =>
      expect(fetchThreads).toHaveBeenCalledWith({ conversation: 'whisper:3,9', after: undefined })
    );
  });

  it('passes the pressed thread to onOpenThread', async () => {
    const user = userEvent.setup();
    const onOpenThread = vi.fn();
    vi.spyOn(playQueries, 'fetchPlayThreads').mockResolvedValue(page([thread()]));
    renderWithClient(
      <ConversationThreadList conversationKey="scene:412" onOpenThread={onOpenThread} />
    );
    await user.click(await screen.findByRole('button', { name: /You came anyway/ }));
    expect(onOpenThread).toHaveBeenCalledWith(expect.objectContaining({ id: 'thread-1' }));
  });

  it('labels a thread by its poses when the opening pose is not readable', async () => {
    vi.spyOn(playQueries, 'fetchPlayThreads').mockResolvedValue(
      page([thread({ opening: '', unread: 0 })])
    );
    renderWithClient(
      <ConversationThreadList conversationKey="scene:412" onOpenThread={() => {}} />
    );
    expect(await screen.findByRole('button', { name: /4 poses from/ })).toBeInTheDocument();
  });

  it('says so when the conversation has no reply threads', async () => {
    vi.spyOn(playQueries, 'fetchPlayThreads').mockResolvedValue(page([]));
    renderWithClient(
      <ConversationThreadList conversationKey="scene:412" onOpenThread={() => {}} />
    );
    expect(await screen.findByText(/Every pose here stands on its own/i)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /next page/i })).not.toBeInTheDocument();
  });

  it('pages with the cursor when more threads are available', async () => {
    const user = userEvent.setup();
    const fetchThreads = vi
      .spyOn(playQueries, 'fetchPlayThreads')
      .mockResolvedValue(page([thread()], 'cursor-2'));
    renderWithClient(
      <ConversationThreadList conversationKey="scene:412" onOpenThread={() => {}} />
    );
    await user.click(await screen.findByRole('button', { name: /next page/i }));
    await waitFor(() =>
      expect(fetchThreads).toHaveBeenCalledWith({ conversation: 'scene:412', after: 'cursor-2' })
    );
  });

  it('reports how many threads it loaded', async () => {
    const onCountLoaded = vi.fn();
    vi.spyOn(playQueries, 'fetchPlayThreads').mockResolvedValue(
      page([thread(), thread({ id: 'thread-2' })])
    );
    renderWithClient(
      <ConversationThreadList
        conversationKey="scene:412"
        onOpenThread={() => {}}
        onCountLoaded={onCountLoaded}
      />
    );
    await waitFor(() => expect(onCountLoaded).toHaveBeenCalledWith(2));
  });

  it('reports the count again on a cache-served remount, without refetching', async () => {
    const onCountLoaded = vi.fn();
    const fetchThreads = vi
      .spyOn(playQueries, 'fetchPlayThreads')
      .mockResolvedValue(page([thread(), thread({ id: 'thread-2' })]));
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const renderRow = () =>
      render(
        <QueryClientProvider client={client}>
          <ConversationThreadList
            conversationKey="scene:412"
            onOpenThread={() => {}}
            onCountLoaded={onCountLoaded}
          />
        </QueryClientProvider>
      );

    const { unmount } = renderRow();
    await waitFor(() => expect(onCountLoaded).toHaveBeenCalledWith(2));
    expect(fetchThreads).toHaveBeenCalledTimes(1);
    unmount();

    // Same QueryClient, so `staleTime` is still fresh and this remount is served
    // entirely from cache: `queryFn` must not run again, yet the count still
    // needs to reach the caller.
    renderRow();
    await waitFor(() => expect(onCountLoaded).toHaveBeenCalledTimes(2));
    expect(fetchThreads).toHaveBeenCalledTimes(1);
  });
});

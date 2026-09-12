import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { HistoryNavigator } from './HistoryNavigator';
import * as playQueries from '../playQueries';

function renderWithClient(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

function conversation(overrides = {}) {
  return {
    ref: { kind: 'room' as const, key: 'scene:412' },
    title: 'Scene 412',
    availability: 'retained' as const,
    canRead: true,
    canSend: false,
    sceneId: '412',
    latestVisiblePose: { id: '18', timestamp: '2026-06-14T10:40:00Z' },
    unread: 3,
    directUnread: 0,
    ...overrides,
  };
}

describe('HistoryNavigator', () => {
  beforeEach(() => {
    vi.spyOn(playQueries, 'fetchPlaySearch').mockResolvedValue({
      results: [],
      before: null,
      after: null,
      snapshot: '2026-01-01T00:00:00Z',
    });
    vi.spyOn(playQueries, 'fetchPlayConversations').mockResolvedValue({
      results: [],
      before: null,
      after: null,
      snapshot: '2026-01-01T00:00:00Z',
    });
  });

  it('offers a type selector including All accessible', () => {
    renderWithClient(<HistoryNavigator />);
    expect(screen.getByRole('combobox', { name: /type/i })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: /all accessible/i })).toBeInTheDocument();
  });

  it('search always sends a date bound by default', async () => {
    const user = userEvent.setup();
    renderWithClient(<HistoryNavigator />);
    await user.type(screen.getByRole('textbox', { name: /search history/i }), 'caravan');
    await user.click(screen.getByRole('button', { name: /search history/i }));
    expect(playQueries.fetchPlaySearch).toHaveBeenCalledWith(
      'caravan',
      expect.any(String),
      undefined,
      undefined
    );
  });

  it('shows a Next page control when the conversations page has an after cursor', async () => {
    vi.spyOn(playQueries, 'fetchPlayConversations').mockResolvedValue({
      results: [
        {
          ref: { kind: 'room', key: 'scene:1' },
          title: 'Scene 1',
          availability: 'retained',
          canRead: true,
          canSend: false,
          sceneId: '1',
          latestVisiblePose: { id: '1', timestamp: '2026-01-01T00:00:00Z' },
          unread: 0,
          directUnread: 0,
        },
      ],
      before: null,
      after: 'cursor-token',
      snapshot: '2026-01-01T00:00:00Z',
    });
    renderWithClient(<HistoryNavigator />);
    expect(await screen.findByRole('button', { name: /next page/i })).toBeInTheDocument();
  });

  it('resets the conversations cursor to page 1 when the From date filter changes', async () => {
    const user = userEvent.setup();
    vi.spyOn(playQueries, 'fetchPlayConversations').mockResolvedValue({
      results: [
        {
          ref: { kind: 'room', key: 'scene:1' },
          title: 'Scene 1',
          availability: 'retained',
          canRead: true,
          canSend: false,
          sceneId: '1',
          latestVisiblePose: { id: '1', timestamp: '2026-01-01T00:00:00Z' },
          unread: 0,
          directUnread: 0,
        },
      ],
      before: null,
      after: 'cursor-token',
      snapshot: '2026-01-01T00:00:00Z',
    });
    renderWithClient(<HistoryNavigator />);

    // Page forward: click Next page, which sets the cursor.
    await user.click(await screen.findByRole('button', { name: /next page/i }));
    await waitFor(() =>
      expect(playQueries.fetchPlayConversations).toHaveBeenLastCalledWith(
        expect.objectContaining({ after: 'cursor-token' })
      )
    );

    // Changing the From date is an unrelated-to-showAllHistory filter change
    // that scopes the same conversations query — it must reset paging back
    // to page 1, not keep requesting page N+1 of the new filter.
    const fromInput = screen.getByLabelText(/from/i);
    await user.type(fromInput, '2026-01-15');

    await waitFor(() =>
      expect(playQueries.fetchPlayConversations).toHaveBeenLastCalledWith(
        expect.objectContaining({ after: undefined })
      )
    );
  });

  it('does not reset the cursor on an unrelated re-render (only on a genuine filter change)', async () => {
    const user = userEvent.setup();
    vi.spyOn(playQueries, 'fetchPlayConversations').mockResolvedValue({
      results: [
        {
          ref: { kind: 'room', key: 'scene:1' },
          title: 'Scene 1',
          availability: 'retained',
          canRead: true,
          canSend: false,
          sceneId: '1',
          latestVisiblePose: { id: '1', timestamp: '2026-01-01T00:00:00Z' },
          unread: 0,
          directUnread: 0,
        },
      ],
      before: null,
      after: 'cursor-token',
      snapshot: '2026-01-01T00:00:00Z',
    });
    renderWithClient(<HistoryNavigator />);

    await user.click(await screen.findByRole('button', { name: /next page/i }));
    await waitFor(() =>
      expect(playQueries.fetchPlayConversations).toHaveBeenLastCalledWith(
        expect.objectContaining({ after: 'cursor-token' })
      )
    );

    // Typing in the search box (unrelated to the conversations list's own
    // from/to filters) re-renders the component but must NOT clobber the
    // cursor that's already mid-page.
    await user.type(screen.getByRole('textbox', { name: /search history/i }), 'caravan');

    expect(playQueries.fetchPlayConversations).toHaveBeenLastCalledWith(
      expect.objectContaining({ after: 'cursor-token' })
    );
  });

  it('resets the cursor exactly once, synchronously with the From filter change (#3759 review fold-in 7b)', async () => {
    // The cursor reset now lives directly in the From/To onChange handlers
    // (alongside setFrom/setTo), not a useEffect keyed on [from, to] -- a
    // `useEffect` fires one render AFTER the state change lands, so
    // react-query would fire once with the stale cursor and once with the
    // reset one (a wasted, silently-dropped request). This asserts the
    // FIRST conversations fetch following the filter change already carries
    // the reset cursor -- there is no interim fetch with the stale one.
    const user = userEvent.setup();
    vi.spyOn(playQueries, 'fetchPlayConversations').mockResolvedValue({
      results: [
        {
          ref: { kind: 'room', key: 'scene:1' },
          title: 'Scene 1',
          availability: 'retained',
          canRead: true,
          canSend: false,
          sceneId: '1',
          latestVisiblePose: { id: '1', timestamp: '2026-01-01T00:00:00Z' },
          unread: 0,
          directUnread: 0,
        },
      ],
      before: null,
      after: 'cursor-token',
      snapshot: '2026-01-01T00:00:00Z',
    });
    renderWithClient(<HistoryNavigator />);

    await user.click(await screen.findByRole('button', { name: /next page/i }));
    await waitFor(() =>
      expect(playQueries.fetchPlayConversations).toHaveBeenLastCalledWith(
        expect.objectContaining({ after: 'cursor-token' })
      )
    );
    const callsBeforeFilterChange = vi.mocked(playQueries.fetchPlayConversations).mock.calls.length;

    const fromInput = screen.getByLabelText(/from/i);
    await user.type(fromInput, '2026-01-15');

    await waitFor(() =>
      expect(playQueries.fetchPlayConversations).toHaveBeenLastCalledWith(
        expect.objectContaining({ after: undefined })
      )
    );
    // Every fetch fired since the filter change already carries the reset
    // cursor -- none of them repeats the stale 'cursor-token' value, which a
    // one-render-late effect would have produced for the FIRST of these.
    const callsAfterFilterChange = vi
      .mocked(playQueries.fetchPlayConversations)
      .mock.calls.slice(callsBeforeFilterChange);
    expect(callsAfterFilterChange.length).toBeGreaterThan(0);
    for (const [params] of callsAfterFilterChange) {
      expect(params).toEqual(expect.objectContaining({ after: undefined }));
    }
  });

  it('does not ask for threads until the Threads control is pressed', async () => {
    const fetchThreads = vi.spyOn(playQueries, 'fetchPlayThreads').mockResolvedValue({
      results: [],
      before: null,
      after: null,
      snapshot: '2026-06-14T12:00:00Z',
    });
    vi.spyOn(playQueries, 'fetchPlayConversations').mockResolvedValue({
      results: [conversation()],
      before: null,
      after: null,
      snapshot: '2026-06-14T12:00:00Z',
    });
    renderWithClient(<HistoryNavigator />);
    expect(await screen.findByText('Scene 412')).toBeInTheDocument();
    expect(fetchThreads).not.toHaveBeenCalled();
    await userEvent.setup().click(screen.getByRole('button', { name: /threads/i }));
    await waitFor(() => expect(fetchThreads).toHaveBeenCalled());
  });

  it("opens a pressed thread in reference mode at the thread's first visible pose", async () => {
    const user = userEvent.setup();
    const onOpenReference = vi.fn();
    vi.spyOn(playQueries, 'fetchPlayConversations').mockResolvedValue({
      results: [conversation()],
      before: null,
      after: null,
      snapshot: '2026-06-14T12:00:00Z',
    });
    vi.spyOn(playQueries, 'fetchPlayThreads').mockResolvedValue({
      results: [
        {
          id: 'thread-1',
          conversation: { kind: 'room', key: 'scene:412' },
          root: { id: '11', timestamp: '2026-06-14T10:00:00Z' },
          firstVisible: { id: '11', timestamp: '2026-06-14T10:00:00Z' },
          latestVisible: { id: '18', timestamp: '2026-06-14T10:40:00Z' },
          opening: 'You came anyway. I did wonder.',
          visiblePoseCount: 4,
          unread: 2,
          directUnread: 0,
        },
      ],
      before: null,
      after: null,
      snapshot: '2026-06-14T12:00:00Z',
    });
    renderWithClient(<HistoryNavigator onOpenReference={onOpenReference} />);
    await user.click(await screen.findByRole('button', { name: /threads/i }));
    await user.click(await screen.findByRole('button', { name: /You came anyway/ }));
    expect(onOpenReference).toHaveBeenCalledWith({
      kind: 'room',
      key: 'scene:412',
      title: 'Scene 412',
      poseId: '11',
      timestamp: '2026-06-14T10:00:00Z',
    });
  });

  it('offers no Threads control on a conversation it cannot read', async () => {
    vi.spyOn(playQueries, 'fetchPlayConversations').mockResolvedValue({
      results: [conversation({ canRead: false, unread: 0 })],
      before: null,
      after: null,
      snapshot: '2026-06-14T12:00:00Z',
    });
    renderWithClient(<HistoryNavigator />);
    expect(await screen.findByText('Scene 412')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /threads/i })).not.toBeInTheDocument();
  });

  it('keeps the search text and date filters while a thread list is open', async () => {
    const user = userEvent.setup();
    vi.spyOn(playQueries, 'fetchPlayConversations').mockResolvedValue({
      results: [conversation()],
      before: null,
      after: null,
      snapshot: '2026-06-14T12:00:00Z',
    });
    vi.spyOn(playQueries, 'fetchPlayThreads').mockResolvedValue({
      results: [],
      before: null,
      after: null,
      snapshot: '2026-06-14T12:00:00Z',
    });
    renderWithClient(<HistoryNavigator />);
    const search = screen.getByRole('textbox', { name: /search history/i });
    await user.type(search, 'arbour');
    await user.click(await screen.findByRole('button', { name: /threads/i }));
    expect(await screen.findByText(/Every pose here stands on its own/i)).toBeInTheDocument();
    expect(search).toHaveValue('arbour');
  });
});

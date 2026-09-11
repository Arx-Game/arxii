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

  it('shows a Load more control when the conversations page has an after cursor', async () => {
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
    expect(await screen.findByRole('button', { name: /load more/i })).toBeInTheDocument();
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

    // Page forward: click Load more, which sets the cursor.
    await user.click(await screen.findByRole('button', { name: /load more/i }));
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

  it('does not reset the cursor on every re-render (only on a genuine filter change)', async () => {
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

    await user.click(await screen.findByRole('button', { name: /load more/i }));
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
});

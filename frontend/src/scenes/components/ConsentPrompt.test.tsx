import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import type { ActionRequest } from '../actionTypes';

vi.mock('../actionQueries', () => ({
  fetchPendingRequests: vi.fn(),
  respondToRequest: vi.fn(),
}));

import { fetchPendingRequests, respondToRequest } from '../actionQueries';
import { ConsentPrompt } from './ConsentPrompt';

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

const MOCK_REQUEST: ActionRequest = {
  id: 7,
  initiator_persona: { id: 1, name: 'Darth Maul' },
  action_name: 'Intimidate',
  technique_name: null,
  created_at: '2026-03-22T12:00:00Z',
};

const MOCK_REQUEST_WITH_TECHNIQUE: ActionRequest = {
  id: 8,
  initiator_persona: { id: 2, name: 'Gandalf' },
  action_name: 'Enchant',
  technique_name: 'Mind Whisper',
  created_at: '2026-03-22T12:05:00Z',
};

describe('ConsentPrompt', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows nothing when no pending requests', async () => {
    vi.mocked(fetchPendingRequests).mockResolvedValue({ results: [] });

    const { container } = render(<ConsentPrompt sceneId="42" />, {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(fetchPendingRequests).toHaveBeenCalledWith('42');
    });

    // Component returns null when empty
    expect(container.innerHTML).toBe('');
  });

  it('shows prompt when a pending request exists', async () => {
    vi.mocked(fetchPendingRequests).mockResolvedValue({ results: [MOCK_REQUEST] });

    render(<ConsentPrompt sceneId="42" />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getByText('Darth Maul')).toBeInTheDocument();
    });
    expect(screen.getByText('Intimidate')).toBeInTheDocument();
  });

  it('displays initiator name and action name', async () => {
    vi.mocked(fetchPendingRequests).mockResolvedValue({ results: [MOCK_REQUEST] });

    render(<ConsentPrompt sceneId="42" />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getByText('Darth Maul')).toBeInTheDocument();
    });
    expect(screen.getByText('Intimidate')).toBeInTheDocument();
    expect(screen.getByText(/on your character/)).toBeInTheDocument();
  });

  it('displays technique name when present', async () => {
    vi.mocked(fetchPendingRequests).mockResolvedValue({
      results: [MOCK_REQUEST_WITH_TECHNIQUE],
    });

    render(<ConsentPrompt sceneId="42" />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getByText('Gandalf')).toBeInTheDocument();
    });
    expect(screen.getByText(/Mind Whisper/)).toBeInTheDocument();
  });

  it('clicking Deny calls respondToRequest with accept: false', async () => {
    vi.mocked(fetchPendingRequests).mockResolvedValue({ results: [MOCK_REQUEST] });
    vi.mocked(respondToRequest).mockResolvedValue({ status: 'resolved' });
    const user = userEvent.setup();

    render(<ConsentPrompt sceneId="42" />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getByText('Deny')).toBeInTheDocument();
    });

    await user.click(screen.getByText('Deny'));

    await waitFor(() => {
      expect(respondToRequest).toHaveBeenCalledWith('42', 7, {
        accept: false,
      });
    });
  });

  it('clicking Standard accept calls respondToRequest with accept: true and standard difficulty', async () => {
    vi.mocked(fetchPendingRequests).mockResolvedValue({ results: [MOCK_REQUEST] });
    vi.mocked(respondToRequest).mockResolvedValue({ status: 'resolved' });
    const user = userEvent.setup();

    render(<ConsentPrompt sceneId="42" />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getByText('Standard')).toBeInTheDocument();
    });

    await user.click(screen.getByText('Standard'));

    await waitFor(() => {
      expect(respondToRequest).toHaveBeenCalledWith('42', 7, {
        accept: true,
        difficulty: 'standard',
      });
    });
  });

  it('clicking Easy accept calls respondToRequest with easy difficulty', async () => {
    vi.mocked(fetchPendingRequests).mockResolvedValue({ results: [MOCK_REQUEST] });
    vi.mocked(respondToRequest).mockResolvedValue({ status: 'resolved' });
    const user = userEvent.setup();

    render(<ConsentPrompt sceneId="42" />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getByText('Easy')).toBeInTheDocument();
    });

    await user.click(screen.getByText('Easy'));

    await waitFor(() => {
      expect(respondToRequest).toHaveBeenCalledWith('42', 7, {
        accept: true,
        difficulty: 'easy',
      });
    });
  });

  it('clicking Hard accept calls respondToRequest with hard difficulty', async () => {
    vi.mocked(fetchPendingRequests).mockResolvedValue({ results: [MOCK_REQUEST] });
    vi.mocked(respondToRequest).mockResolvedValue({ status: 'resolved' });
    const user = userEvent.setup();

    render(<ConsentPrompt sceneId="42" />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getByText('Hard')).toBeInTheDocument();
    });

    await user.click(screen.getByText('Hard'));

    await waitFor(() => {
      expect(respondToRequest).toHaveBeenCalledWith('42', 7, {
        accept: true,
        difficulty: 'hard',
      });
    });
  });

  it('renders multiple pending requests', async () => {
    vi.mocked(fetchPendingRequests).mockResolvedValue({
      results: [MOCK_REQUEST, MOCK_REQUEST_WITH_TECHNIQUE],
    });

    render(<ConsentPrompt sceneId="42" />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getByText('Darth Maul')).toBeInTheDocument();
    });
    expect(screen.getByText('Gandalf')).toBeInTheDocument();
  });
});

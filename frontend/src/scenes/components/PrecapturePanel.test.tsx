import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import type { ReactNode } from 'react';
import type { PrecapturePreviewInteraction } from '../types';

const mockFetchPrecapturedInteractions = vi.fn();
const mockTruncatePrecapture = vi.fn();
vi.mock('../precaptureQueries', () => ({
  fetchPrecapturedInteractions: (...args: unknown[]) => mockFetchPrecapturedInteractions(...args),
  truncatePrecapture: (...args: unknown[]) => mockTruncatePrecapture(...args),
}));

import { PrecapturePanel } from './PrecapturePanel';

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

const POSE_A: PrecapturePreviewInteraction = {
  id: 10,
  persona_name: 'Alice',
  content: 'Alice waits by the fountain.',
  mode: 'pose',
  timestamp: '2026-08-08T11:40:00Z',
};

const POSE_B: PrecapturePreviewInteraction = {
  id: 11,
  persona_name: 'Bob',
  content: 'Bob arrives, breathless.',
  mode: 'pose',
  timestamp: '2026-08-08T11:50:00Z',
};

describe('PrecapturePanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders nothing when there is nothing captured', async () => {
    mockFetchPrecapturedInteractions.mockResolvedValue([]);

    const { container } = render(<PrecapturePanel sceneId="42" />, { wrapper: createWrapper() });

    await waitFor(() => expect(mockFetchPrecapturedInteractions).toHaveBeenCalledWith('42'));
    expect(container.querySelector('[data-testid="precapture-panel"]')).toBeNull();
  });

  it('lists every captured pose, oldest first as returned by the API', async () => {
    mockFetchPrecapturedInteractions.mockResolvedValue([POSE_A, POSE_B]);

    render(<PrecapturePanel sceneId="42" />, { wrapper: createWrapper() });

    await waitFor(() => expect(screen.getByTestId('precapture-panel')).toBeInTheDocument());
    const rows = screen.getAllByTestId('precapture-row');
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent('Alice');
    expect(rows[1]).toHaveTextContent('Bob');
  });

  it('clicking "Start scene from here" truncates using that pose\'s id', async () => {
    mockFetchPrecapturedInteractions.mockResolvedValue([POSE_A, POSE_B]);
    mockTruncatePrecapture.mockResolvedValue({});
    const user = userEvent.setup();

    render(<PrecapturePanel sceneId="42" />, { wrapper: createWrapper() });

    await waitFor(() => expect(screen.getAllByTestId('precapture-truncate-btn')).toHaveLength(2));

    await user.click(screen.getAllByTestId('precapture-truncate-btn')[1]);

    await waitFor(() => {
      expect(mockTruncatePrecapture).toHaveBeenCalledWith('42', POSE_B.id);
    });
  });

  it('does not call truncate for a pose that was never clicked', async () => {
    mockFetchPrecapturedInteractions.mockResolvedValue([POSE_A, POSE_B]);
    mockTruncatePrecapture.mockResolvedValue({});
    const user = userEvent.setup();

    render(<PrecapturePanel sceneId="42" />, { wrapper: createWrapper() });

    await waitFor(() => expect(screen.getAllByTestId('precapture-truncate-btn')).toHaveLength(2));
    await user.click(screen.getAllByTestId('precapture-truncate-btn')[0]);

    await waitFor(() => expect(mockTruncatePrecapture).toHaveBeenCalledTimes(1));
    expect(mockTruncatePrecapture).toHaveBeenCalledWith('42', POSE_A.id);
    expect(mockTruncatePrecapture).not.toHaveBeenCalledWith('42', POSE_B.id);
  });
});

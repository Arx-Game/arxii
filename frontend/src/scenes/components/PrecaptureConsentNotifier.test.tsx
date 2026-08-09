import { render, waitFor, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import type { ReactNode } from 'react';
import type { PrecaptureConsentRequest } from '../types';

const mockFetchPendingPrecaptureConsents = vi.fn();
const mockRespondToPrecaptureConsent = vi.fn();
vi.mock('../precaptureQueries', () => ({
  fetchPendingPrecaptureConsents: (...args: unknown[]) =>
    mockFetchPendingPrecaptureConsents(...args),
  respondToPrecaptureConsent: (...args: unknown[]) => mockRespondToPrecaptureConsent(...args),
}));

const toastCustomMock = vi.fn();
vi.mock('sonner', () => ({
  toast: Object.assign(vi.fn(), {
    custom: (...args: unknown[]) => toastCustomMock(...args),
    dismiss: vi.fn(),
  }),
}));

import { PrecaptureConsentNotifier } from './PrecaptureConsentNotifier';

function request(id: number, overrides: Partial<PrecaptureConsentRequest> = {}) {
  return {
    id,
    scene: 1,
    scene_name: 'A Scene',
    room_name: 'The Garden',
    status: 'pending' as const,
    requested_at: '2026-08-08T12:00:00Z',
    responded_at: null,
    candidates: [
      {
        id: 100 + id,
        persona_name: 'Alice',
        content: 'Alice waits by the fountain.',
        mode: 'pose',
        timestamp: '2026-08-08T11:45:00Z',
      },
    ],
    ...overrides,
  };
}

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

describe('PrecaptureConsentNotifier', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockFetchPendingPrecaptureConsents.mockResolvedValue([]);
  });

  it('renders nothing itself', async () => {
    const { container } = render(<PrecaptureConsentNotifier />, { wrapper: createWrapper() });
    await waitFor(() => expect(mockFetchPendingPrecaptureConsents).toHaveBeenCalled());
    expect(container.innerHTML).toBe('');
  });

  it('fires one custom toast per newly-seen pending request', async () => {
    mockFetchPendingPrecaptureConsents.mockResolvedValue([request(1)]);

    render(<PrecaptureConsentNotifier />, { wrapper: createWrapper() });

    await waitFor(() => expect(toastCustomMock).toHaveBeenCalledTimes(1));
  });

  it('does not re-fire for a request id already toasted', async () => {
    mockFetchPendingPrecaptureConsents.mockResolvedValue([request(1)]);
    const wrapper = createWrapper();
    const { rerender } = render(<PrecaptureConsentNotifier />, { wrapper });
    await waitFor(() => expect(toastCustomMock).toHaveBeenCalledTimes(1));

    rerender(<PrecaptureConsentNotifier />);
    expect(toastCustomMock).toHaveBeenCalledTimes(1);
  });

  it('fires one toast per distinct pending request id in a single poll', async () => {
    mockFetchPendingPrecaptureConsents.mockResolvedValue([request(1), request(2)]);

    render(<PrecaptureConsentNotifier />, { wrapper: createWrapper() });

    await waitFor(() => expect(toastCustomMock).toHaveBeenCalledTimes(2));
  });

  it('the toast body shows the room and the candidate count', async () => {
    mockFetchPendingPrecaptureConsents.mockResolvedValue([request(1)]);
    render(<PrecaptureConsentNotifier />, { wrapper: createWrapper() });

    await waitFor(() => expect(toastCustomMock).toHaveBeenCalledTimes(1));
    const renderFn = toastCustomMock.mock.calls[0][0] as (id: string | number) => JSX.Element;
    const { getByText } = render(renderFn('toast-1'));

    expect(getByText(/The Garden/)).toBeInTheDocument();
    expect(getByText(/1 of your recent pose/)).toBeInTheDocument();
  });

  it('accepting posts accept:true', async () => {
    mockFetchPendingPrecaptureConsents.mockResolvedValue([request(1)]);
    mockRespondToPrecaptureConsent.mockResolvedValue({ attached_count: 1, status: 'accepted' });
    render(<PrecaptureConsentNotifier />, { wrapper: createWrapper() });

    await waitFor(() => expect(toastCustomMock).toHaveBeenCalledTimes(1));
    const renderFn = toastCustomMock.mock.calls[0][0] as (id: string | number) => JSX.Element;
    const { getByTestId } = render(renderFn('toast-1'));

    fireEvent.click(getByTestId('precapture-toast-accept-btn'));

    await waitFor(() => {
      expect(mockRespondToPrecaptureConsent).toHaveBeenCalledWith(1, true);
    });
  });

  it('declining posts accept:false', async () => {
    mockFetchPendingPrecaptureConsents.mockResolvedValue([request(1)]);
    mockRespondToPrecaptureConsent.mockResolvedValue({ attached_count: 0, status: 'denied' });
    render(<PrecaptureConsentNotifier />, { wrapper: createWrapper() });

    await waitFor(() => expect(toastCustomMock).toHaveBeenCalledTimes(1));
    const renderFn = toastCustomMock.mock.calls[0][0] as (id: string | number) => JSX.Element;
    const { getByTestId } = render(renderFn('toast-1'));

    fireEvent.click(getByTestId('precapture-toast-decline-btn'));

    await waitFor(() => {
      expect(mockRespondToPrecaptureConsent).toHaveBeenCalledWith(1, false);
    });
  });

  it('shows an inline error and does not throw when the response fails', async () => {
    mockFetchPendingPrecaptureConsents.mockResolvedValue([request(1)]);
    mockRespondToPrecaptureConsent.mockRejectedValue(new Error('Network error'));
    render(<PrecaptureConsentNotifier />, { wrapper: createWrapper() });

    await waitFor(() => expect(toastCustomMock).toHaveBeenCalledTimes(1));
    const renderFn = toastCustomMock.mock.calls[0][0] as (id: string | number) => JSX.Element;
    const { getByTestId } = render(renderFn('toast-1'));

    fireEvent.click(getByTestId('precapture-toast-accept-btn'));

    await waitFor(() => {
      expect(getByTestId('precapture-toast-error')).toHaveTextContent('Network error');
    });
  });
});

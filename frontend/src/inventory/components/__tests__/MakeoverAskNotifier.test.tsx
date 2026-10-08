import { render, waitFor, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import type { ReactNode } from 'react';
import { Provider } from 'react-redux';
import { configureStore } from '@reduxjs/toolkit';
import { authSlice, setAccount } from '@/store/authSlice';
import { mockAccount } from '@/test/mocks/account';
import type { MakeoverConsentRequest } from '../../makeoverRequests';

const mockFetchPendingMakeoverRequests = vi.fn();
const mockRespondToMakeoverRequest = vi.fn();
vi.mock('../../makeoverRequests', () => ({
  MAKEOVER_REQUESTS_QUERY_KEY: ['makeover-requests'],
  fetchPendingMakeoverRequests: (...args: unknown[]) => mockFetchPendingMakeoverRequests(...args),
  respondToMakeoverRequest: (...args: unknown[]) => mockRespondToMakeoverRequest(...args),
}));

const toastCustomMock = vi.fn();
vi.mock('sonner', () => ({
  toast: Object.assign(vi.fn(), {
    custom: (...args: unknown[]) => toastCustomMock(...args),
    dismiss: vi.fn(),
  }),
}));

import { MakeoverAskNotifier } from '../MakeoverAskNotifier';

function ask(id: number): MakeoverConsentRequest {
  return {
    id,
    stylist_name: 'Nyx',
    item_name: 'a silver styling kit',
    trait_name: 'hair',
    option_name: 'crimson',
    blend: false,
    descriptor: '',
    description: 'Nyx offers to restyle your hair (crimson) with a silver styling kit.',
    target_character_id: 42,
    requested_at: '2026-10-07T12:00:00Z',
  };
}

function createWrapper(loggedIn = true) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const store = configureStore({ reducer: { auth: authSlice.reducer } });
  if (loggedIn) store.dispatch(setAccount(mockAccount));
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <Provider store={store}>
        <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
      </Provider>
    );
  };
}

async function renderToast() {
  mockFetchPendingMakeoverRequests.mockResolvedValue([ask(1)]);
  render(<MakeoverAskNotifier />, { wrapper: createWrapper() });
  await waitFor(() => expect(toastCustomMock).toHaveBeenCalledTimes(1));
  const renderFn = toastCustomMock.mock.calls[0][0] as (id: string | number) => JSX.Element;
  return render(renderFn('toast-1'));
}

describe('MakeoverAskNotifier', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockFetchPendingMakeoverRequests.mockResolvedValue([]);
    mockRespondToMakeoverRequest.mockResolvedValue({ status: 'accepted' });
  });

  it('does not fetch while logged out', async () => {
    render(<MakeoverAskNotifier />, { wrapper: createWrapper(false) });
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(mockFetchPendingMakeoverRequests).not.toHaveBeenCalled();
  });

  it('fires one toast per newly seen ask and never twice for one id', async () => {
    mockFetchPendingMakeoverRequests.mockResolvedValue([ask(1), ask(2)]);
    const wrapper = createWrapper();
    const { rerender } = render(<MakeoverAskNotifier />, { wrapper });
    await waitFor(() => expect(toastCustomMock).toHaveBeenCalledTimes(2));
    rerender(<MakeoverAskNotifier />);
    expect(toastCustomMock).toHaveBeenCalledTimes(2);
  });

  it('the toast shows the offer and the four answers', async () => {
    const { getByTestId, getByText } = await renderToast();
    expect(getByText(/Nyx offers to restyle your hair \(crimson\)/)).toBeInTheDocument();
    expect(getByTestId('makeover-ask-grant')).toHaveTextContent('Grant');
    expect(getByTestId('makeover-ask-decline')).toHaveTextContent('Decline');
    expect(getByTestId('makeover-ask-always')).toHaveTextContent('Always let Nyx');
    expect(getByTestId('makeover-ask-never')).toHaveTextContent('Never from Nyx');
  });

  it('Grant posts grant with no shortcut', async () => {
    const { getByTestId } = await renderToast();
    fireEvent.click(getByTestId('makeover-ask-grant'));
    await waitFor(() =>
      expect(mockRespondToMakeoverRequest).toHaveBeenCalledWith(1, 'grant', null)
    );
  });

  it('Always let posts grant with always', async () => {
    const { getByTestId } = await renderToast();
    fireEvent.click(getByTestId('makeover-ask-always'));
    await waitFor(() =>
      expect(mockRespondToMakeoverRequest).toHaveBeenCalledWith(1, 'grant', 'always')
    );
  });

  it('Never from posts decline with never', async () => {
    const { getByTestId } = await renderToast();
    fireEvent.click(getByTestId('makeover-ask-never'));
    await waitFor(() =>
      expect(mockRespondToMakeoverRequest).toHaveBeenCalledWith(1, 'decline', 'never')
    );
  });

  it('shows an inline error when the answer fails', async () => {
    mockRespondToMakeoverRequest.mockRejectedValue(new Error('They are no longer here to do it.'));
    const { getByTestId } = await renderToast();
    fireEvent.click(getByTestId('makeover-ask-grant'));
    await waitFor(() =>
      expect(getByTestId('makeover-ask-error')).toHaveTextContent('no longer here')
    );
  });
});

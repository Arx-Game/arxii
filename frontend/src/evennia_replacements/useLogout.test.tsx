/**
 * Logout must leave the guarded page and land on the home route (#3592).
 *
 * Reported on play.arx2.com: logging out from the profile dropdown while on
 * a staff page left the staff page on screen. This is an integration test
 * over the real pieces that decide that: a real QueryClient (the guards read
 * the `['account']` query), the real Redux store, a MemoryRouter, and the
 * real StaffRoute wrapping a button that fires `useLogout`. Only `./api`
 * (network) and `useGameSocket` (real WebSocket) are mocked.
 */
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Provider } from 'react-redux';
import { MemoryRouter, Routes, Route, useLocation } from 'react-router-dom';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

vi.mock('./api', () => ({
  fetchAccount: vi.fn(),
  fetchRegistrationStatus: vi.fn(),
  postLogin: vi.fn(),
  postLogout: vi.fn(),
  postRegister: vi.fn(),
}));

const disconnectAllMock = vi.fn();
vi.mock('@/hooks/useGameSocket', () => ({
  useGameSocket: () => ({
    connect: vi.fn(),
    send: vi.fn(),
    disconnectAll: disconnectAllMock,
    executeAction: vi.fn(),
  }),
}));

import { fetchAccount, postLogout } from './api';
import { useLogout } from './queries';
import { StaffRoute } from '@/components/StaffRoute';
import { mockStaffAccount } from '@/test/mocks/account';
import { store } from '@/store/store';
import { resetGame } from '@/store/gameSlice';
import { setAccount } from '@/store/authSlice';

function LogoutButton() {
  const logout = useLogout();
  return (
    <button type="button" onClick={() => logout.mutate()}>
      Logout
    </button>
  );
}

function LocationProbe() {
  const location = useLocation();
  return <div data-testid="location">{location.pathname}</div>;
}

function renderStaffPageWithLogout() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return render(
    <Provider store={store}>
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/staff/world-builder']}>
          <LocationProbe />
          <Routes>
            <Route
              path="/staff/world-builder"
              element={
                <StaffRoute>
                  <div>Staff content</div>
                  <LogoutButton />
                </StaffRoute>
              }
            />
            <Route path="/login" element={<div>Login page</div>} />
            <Route path="/" element={<div>Home page</div>} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </Provider>
  );
}

describe('useLogout leaves the guarded page (#3592)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    store.dispatch(resetGame());
    store.dispatch(setAccount(mockStaffAccount));
    vi.mocked(fetchAccount).mockResolvedValue(mockStaffAccount);
    vi.mocked(postLogout).mockResolvedValue(undefined);
  });

  afterEach(() => {
    store.dispatch(resetGame());
    store.dispatch(setAccount(null));
  });

  it('unmounts the staff page and lands on the home route after logout', async () => {
    const user = userEvent.setup();
    renderStaffPageWithLogout();

    expect(await screen.findByText('Staff content')).toBeInTheDocument();
    expect(screen.getByTestId('location')).toHaveTextContent('/staff/world-builder');

    // The server session is gone from here on: any refetch sees no account.
    vi.mocked(fetchAccount).mockResolvedValue(null);
    await user.click(screen.getByText('Logout'));

    await waitFor(() => {
      expect(postLogout).toHaveBeenCalledTimes(1);
      expect(screen.queryByText('Staff content')).not.toBeInTheDocument();
    });
    expect(screen.getByTestId('location')).toHaveTextContent('/');
    expect(screen.getByText('Home page')).toBeInTheDocument();
    expect(screen.queryByText('Login page')).not.toBeInTheDocument();
    expect(disconnectAllMock).toHaveBeenCalledTimes(1);
    expect(store.getState().auth.account).toBeNull();
  });
});

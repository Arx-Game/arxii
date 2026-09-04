/**
 * Tests for GMRoute route guard.
 *
 * Verifies GM/staff accounts see the page content while everyone else
 * bounces to "/" (unauthenticated bounces to "/login"). Mirrors the
 * useAuthStatus mock pattern from WardrobePage.test.tsx since StaffRoute
 * (the sibling guard this mirrors) has no test of its own yet.
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { GMRoute } from '../GMRoute';

vi.mock('@/evennia_replacements/queries', () => ({
  useAuthStatus: vi.fn(() => ({ isLoading: false, account: null })),
}));

import * as authQueries from '@/evennia_replacements/queries';

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route
          path={path}
          element={
            <GMRoute>
              <div>Studio content</div>
            </GMRoute>
          }
        />
        <Route path="/login" element={<div>Login page</div>} />
        <Route path="/" element={<div>Home page</div>} />
      </Routes>
    </MemoryRouter>
  );
}

describe('GMRoute', () => {
  it('renders nothing while auth is loading', () => {
    vi.mocked(authQueries.useAuthStatus).mockReturnValue({ isLoading: true, account: null });
    const { container } = renderAt('/stories/scenarios/1/canvas');
    expect(container.textContent).toBe('');
  });

  it('redirects to /login when unauthenticated', () => {
    vi.mocked(authQueries.useAuthStatus).mockReturnValue({ isLoading: false, account: null });
    renderAt('/stories/scenarios/1/canvas');
    expect(screen.getByText('Login page')).toBeInTheDocument();
  });

  it('redirects to / for an account that is neither GM nor staff', () => {
    vi.mocked(authQueries.useAuthStatus).mockReturnValue({
      isLoading: false,
      account: { id: 1, is_gm: false, is_staff: false } as unknown as ReturnType<
        typeof authQueries.useAuthStatus
      >['account'],
    });
    renderAt('/stories/scenarios/1/canvas');
    expect(screen.getByText('Home page')).toBeInTheDocument();
  });

  it('renders children for a GM account', () => {
    vi.mocked(authQueries.useAuthStatus).mockReturnValue({
      isLoading: false,
      account: { id: 1, is_gm: true, is_staff: false } as unknown as ReturnType<
        typeof authQueries.useAuthStatus
      >['account'],
    });
    renderAt('/stories/scenarios/1/canvas');
    expect(screen.getByText('Studio content')).toBeInTheDocument();
  });

  it('renders children for a staff account', () => {
    vi.mocked(authQueries.useAuthStatus).mockReturnValue({
      isLoading: false,
      account: { id: 1, is_gm: false, is_staff: true } as unknown as ReturnType<
        typeof authQueries.useAuthStatus
      >['account'],
    });
    renderAt('/stories/scenarios/1/canvas');
    expect(screen.getByText('Studio content')).toBeInTheDocument();
  });
});

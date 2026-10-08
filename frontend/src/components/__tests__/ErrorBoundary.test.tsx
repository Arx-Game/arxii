/**
 * Tests for ErrorBoundary recovery buttons.
 *
 * Verifies that the error fallback renders "Go Home" and "Reload" buttons
 * in addition to "Try again", so users are never trapped without recovery,
 * and that the fallback renders with no Router above it: main.tsx mounts the
 * root boundary outside BrowserRouter, and a fallback that needed one threw
 * instead of rendering (#4195).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import React from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ErrorBoundary } from '../ErrorBoundary';

function ThrowOnRender({ message }: { message: string }): React.ReactNode {
  throw new Error(message);
}

function renderWithProviders(initialRoute: string = '/') {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  const navigateMock = vi.fn();

  return {
    navigateMock,
    ...render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[initialRoute]}>
          <Routes>
            <Route path="/" element={<div>Home page</div>} />
            <Route
              path="/crash"
              element={
                <ErrorBoundary>
                  <ThrowOnRender message="Test error" />
                </ErrorBoundary>
              }
            />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    ),
  };
}

describe('ErrorBoundary', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders home page when no error', () => {
    renderWithProviders();
    expect(screen.getByText('Home page')).toBeInTheDocument();
  });

  it('shows error message and all three recovery buttons', () => {
    renderWithProviders('/crash');
    expect(screen.getByText('Something went wrong')).toBeInTheDocument();
    expect(screen.getByText('Test error')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /go home/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /reload/i })).toBeInTheDocument();
  });

  it('loads / afresh when Go Home is clicked', async () => {
    const assignSpy = vi.fn();
    Object.defineProperty(window, 'location', {
      value: { assign: assignSpy },
      writable: true,
    });

    renderWithProviders('/crash');
    await userEvent.click(screen.getByRole('button', { name: /go home/i }));
    expect(assignSpy).toHaveBeenCalledWith('/');
  });

  it('renders the fallback with no Router above it, as the root boundary does', () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    render(
      <QueryClientProvider client={queryClient}>
        <ErrorBoundary>
          <ThrowOnRender message="Chrome error" />
        </ErrorBoundary>
      </QueryClientProvider>
    );

    expect(screen.getByText('Something went wrong')).toBeInTheDocument();
    expect(screen.getByText('Chrome error')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /go home/i })).toBeInTheDocument();
    const routerComplaint = errorSpy.mock.calls
      .flat()
      .some((arg) => typeof arg === 'string' && arg.includes('useNavigate'));
    expect(routerComplaint).toBe(false);
  });

  it('calls window.location.reload when Reload is clicked', async () => {
    const reloadSpy = vi.fn();
    Object.defineProperty(window, 'location', {
      value: { reload: reloadSpy },
      writable: true,
    });

    renderWithProviders('/crash');
    await userEvent.click(screen.getByRole('button', { name: /reload/i }));
    expect(reloadSpy).toHaveBeenCalledTimes(1);
  });
});

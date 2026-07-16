/**
 * Tests for ErrorBoundary recovery buttons.
 *
 * Verifies that the error fallback renders "Go Home" and "Reload" buttons
 * in addition to "Try again", so users are never trapped without recovery.
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

  it('navigates to home when Go Home is clicked', async () => {
    renderWithProviders('/crash');
    await userEvent.click(screen.getByRole('button', { name: /go home/i }));
    // After navigation, the error should be cleared and home should render.
    // The ThrowOnRender component's error boundary is reset, and navigation
    // takes us to / which renders "Home page".
    expect(screen.getByText('Home page')).toBeInTheDocument();
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

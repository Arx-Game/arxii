/**
 * Header smoke test — verify navigation links are present.
 */

import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect, vi } from 'vitest';
import type { ReactNode } from 'react';
import { Provider } from 'react-redux';
import { configureStore } from '@reduxjs/toolkit';
import { Header } from '../Header';
import { authSlice } from '@/store/authSlice';
import { gameSlice } from '@/store/gameSlice';
import { rouletteSlice } from '@/store/rouletteSlice';

// Mock the queries that Header uses
vi.mock('@/staff/queries', () => ({
  useOpenSubmissionCount: () => ({
    data: undefined,
  }),
}));

vi.mock('@/narrative/components/UnreadNarrativeBadge', () => ({
  UnreadNarrativeBadge: () => <div data-testid="unread-badge" />,
}));

vi.mock('@/rituals/queries', () => ({
  useRitualSessionInbox: () => ({
    data: [],
  }),
}));

function Wrapper({ children }: { children: ReactNode }) {
  const store = configureStore({
    reducer: {
      auth: authSlice.reducer,
      game: gameSlice.reducer,
      roulette: rouletteSlice.reducer,
    },
  });

  return (
    <Provider store={store}>
      <MemoryRouter>{children}</MemoryRouter>
    </Provider>
  );
}

describe('Header', () => {
  it('renders navigation links including Threads', () => {
    render(
      <Wrapper>
        <Header />
      </Wrapper>
    );

    // Check for main nav links
    expect(screen.getByRole('link', { name: /play/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /roster/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /scenes/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /codex/i })).toBeInTheDocument();

    // Check for Threads link specifically (Task 21)
    expect(screen.getByRole('link', { name: /threads/i })).toBeInTheDocument();
  });
});

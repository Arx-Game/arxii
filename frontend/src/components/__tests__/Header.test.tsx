/**
 * Header smoke test — verify navigation links are present.
 */

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect, vi } from 'vitest';
import type { ReactNode } from 'react';
import { Provider } from 'react-redux';
import { configureStore } from '@reduxjs/toolkit';
import { Header } from '../Header';
import { authSlice } from '@/store/authSlice';
import { gameSlice } from '@/store/gameSlice';
import { rouletteSlice } from '@/store/rouletteSlice';

function setupUser() {
  return { user: userEvent.setup() };
}

// Mock the queries that Header uses
vi.mock('@/staff/queries', () => ({
  useOpenSubmissionCount: () => ({
    data: undefined,
  }),
}));

vi.mock('@/narrative/components/UnreadNarrativeBadge', () => ({
  UnreadNarrativeBadge: () => <div data-testid="unread-badge" />,
}));

vi.mock('@/mail/queries', () => ({
  useUnreadMailCount: () => 0,
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
  it('renders direct nav links and dropdown triggers', () => {
    render(
      <Wrapper>
        <Header />
      </Wrapper>
    );

    // Play is a direct link, always visible
    expect(screen.getByRole('link', { name: /play/i })).toBeInTheDocument();

    // Dropdown group triggers are present as buttons
    expect(screen.getByRole('button', { name: /characters/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /story/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /world/i })).toBeInTheDocument();
  });

  it('renders dropdown links when a group is opened', async () => {
    const { user } = setupUser();
    render(
      <Wrapper>
        <Header />
      </Wrapper>
    );

    // Open the Characters dropdown
    await user.click(screen.getByRole('button', { name: /characters/i }));

    // Links inside the dropdown are now visible
    expect(screen.getByRole('link', { name: /roster/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /progression/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /threads/i })).toBeInTheDocument();
  });

  it('renders Story dropdown links when opened', async () => {
    const { user } = setupUser();
    render(
      <Wrapper>
        <Header />
      </Wrapper>
    );

    await user.click(screen.getByRole('button', { name: /story/i }));

    expect(screen.getByRole('link', { name: /scenes/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /events/i })).toBeInTheDocument();
    // My Stories and Books are auth-only — not logged in, so absent
  });

  it('renders World dropdown links when opened', async () => {
    const { user } = setupUser();
    render(
      <Wrapper>
        <Header />
      </Wrapper>
    );

    await user.click(screen.getByRole('button', { name: /world/i }));

    expect(screen.getByRole('link', { name: /crossover/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /codex/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /tidings/i })).toBeInTheDocument();
  });
});

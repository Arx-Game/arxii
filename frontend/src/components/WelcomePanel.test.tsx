import { screen } from '@testing-library/react';
import { describe, it, expect, vi, afterEach } from 'vitest';

import { WelcomePanel } from './WelcomePanel';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { store } from '@/store/store';
import { setAccount } from '@/store/authSlice';
import { mockAccount } from '@/test/mocks/account';
import type { CharacterDraft } from '@/character-creation/types';

const mockUseDraft = vi.fn();
vi.mock('@/character-creation/queries', () => ({
  useDraft: (...args: unknown[]) => mockUseDraft(...args),
}));

describe('WelcomePanel', () => {
  afterEach(() => {
    store.dispatch(setAccount(null));
    mockUseDraft.mockReset();
    mockUseDraft.mockReturnValue({ data: null });
  });

  it('renders nothing for a guest (no account)', () => {
    mockUseDraft.mockReturnValue({ data: null });
    store.dispatch(setAccount(null));
    const { container } = renderWithProviders(<WelcomePanel />);

    expect(container).toBeEmptyDOMElement();
  });

  it('shows the Enter the game CTA when the account has characters', () => {
    mockUseDraft.mockReturnValue({ data: null });
    store.dispatch(
      setAccount({
        ...mockAccount,
        available_characters: [
          {
            id: 1,
            name: 'Aria',
            portrait_url: null,
            character_type: 'PC',
            roster_status: 'active',
            personas: [],
            last_location: null,
            currently_puppeted_in_session: false,
          },
        ],
      })
    );
    renderWithProviders(<WelcomePanel />);

    expect(screen.getByRole('link', { name: 'Enter the game' })).toHaveAttribute('href', '/game');
  });

  it('shows both CTAs when the account has no characters and no pending applications', () => {
    mockUseDraft.mockReturnValue({ data: null });
    store.dispatch(setAccount({ ...mockAccount }));
    renderWithProviders(<WelcomePanel />);

    expect(screen.getByRole('link', { name: 'Browse the roster' })).toHaveAttribute(
      'href',
      '/roster'
    );
    expect(screen.getByRole('link', { name: 'Create a character' })).toHaveAttribute(
      'href',
      '/characters/create'
    );
    expect(screen.queryByRole('link', { name: 'Enter the game' })).not.toBeInTheDocument();
  });

  it('shows the pending-application status line when applications are pending', () => {
    mockUseDraft.mockReturnValue({ data: null });
    store.dispatch(
      setAccount({
        ...mockAccount,
        pending_applications: [
          {
            id: 5,
            character_id: 12,
            character_name: 'Branwen',
            status: 'pending',
            applied_date: '2026-01-01T00:00:00Z',
          },
        ],
      })
    );
    renderWithProviders(<WelcomePanel />);

    expect(screen.getByText('Your applications')).toBeInTheDocument();
    expect(screen.getByText(/Branwen — pending since/)).toBeInTheDocument();
  });

  it('shows the draft-application link when a draft exists and there are no characters', () => {
    const draft = { id: 9 } as CharacterDraft;
    mockUseDraft.mockReturnValue({ data: draft });
    store.dispatch(setAccount({ ...mockAccount }));
    renderWithProviders(<WelcomePanel />);

    expect(screen.getByRole('link', { name: 'Your character application' })).toHaveAttribute(
      'href',
      '/characters/create/application'
    );
  });
});

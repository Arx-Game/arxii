import { act, screen } from '@testing-library/react';
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';

import { WelcomePanel } from './WelcomePanel';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { store } from '@/store/store';
import { setAccount } from '@/store/authSlice';
import { mockAccount } from '@/test/mocks/account';
import type { CharacterDraft } from '@/character-creation/types';

const mockUseDraft = vi.fn();
const mockUseDraftApplication = vi.fn();
vi.mock('@/character-creation/queries', () => ({
  useDraft: (...args: unknown[]) => mockUseDraft(...args),
  useDraftApplication: (...args: unknown[]) => mockUseDraftApplication(...args),
}));

describe('WelcomePanel', () => {
  afterEach(() => {
    // The panel is still mounted here; the store update re-renders it.
    act(() => {
      store.dispatch(setAccount(null));
    });
    mockUseDraft.mockReset();
    mockUseDraft.mockReturnValue({ data: null });
    mockUseDraftApplication.mockReset();
    mockUseDraftApplication.mockReturnValue({ data: undefined });
  });

  beforeEach(() => {
    mockUseDraftApplication.mockReturnValue({ data: undefined });
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
    expect(screen.getByText(/Branwen: pending since/)).toBeInTheDocument();
  });

  it('shows the application link for a draft that has been submitted', () => {
    const draft = { id: 9 } as CharacterDraft;
    mockUseDraft.mockReturnValue({ data: draft });
    mockUseDraftApplication.mockReturnValue({ data: { id: 3, status: 'submitted' } });
    store.dispatch(setAccount({ ...mockAccount }));
    renderWithProviders(<WelcomePanel />);

    expect(mockUseDraftApplication).toHaveBeenCalledWith(9);
    expect(screen.getByRole('link', { name: 'Your character application' })).toHaveAttribute(
      'href',
      '/characters/create/application'
    );
    // #5207: no space before the colon.
    expect(screen.getByText(/Your character application/).closest('p')).toHaveTextContent(
      'Your character application: check its status.'
    );
    // An application is waiting, so the panel does not also say there is no character yet.
    expect(screen.queryByText(/have a character yet/)).not.toBeInTheDocument();
  });

  // #5207: the application line was shown for any draft, submitted or not.
  it('offers to continue a draft that was never submitted, with no application line', () => {
    mockUseDraft.mockReturnValue({ data: { id: 9 } as CharacterDraft });
    store.dispatch(setAccount({ ...mockAccount }));
    renderWithProviders(<WelcomePanel />);

    expect(screen.queryByRole('link', { name: 'Your character application' })).toBeNull();
    expect(screen.getByRole('link', { name: 'Continue your character' })).toHaveAttribute(
      'href',
      '/characters/create'
    );
    expect(screen.queryByRole('link', { name: 'Create a character' })).toBeNull();
  });
});

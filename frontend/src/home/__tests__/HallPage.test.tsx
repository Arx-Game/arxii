/**
 * HallPage tests (#3412 slice 2) — composition/wiring only. Band internals
 * (CharactersBand/AttentionBand/WorldBand) have their own test suites under
 * `hall/__tests__/`; this file verifies the zero-character remedy swap and
 * that every band mounts with the right data.
 */
import { screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { HallPage } from '../HallPage';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { store } from '@/store/store';
import { setAccount } from '@/store/authSlice';
import type { MyRosterEntry } from '@/roster/types';
import type { AccountData } from '@/evennia_replacements/types';

const mockUseMyRosterEntriesQuery = vi.fn();
vi.mock('@/roster/queries', () => ({
  useMyRosterEntriesQuery: () => mockUseMyRosterEntriesQuery(),
}));

vi.mock('@/components/WelcomePanel', () => ({
  WelcomePanel: () => <div data-testid="welcome-panel-stub" />,
}));

const mockCharactersBand = vi.fn();
vi.mock('../hall/CharactersBand', () => ({
  CharactersBand: (props: { characters: MyRosterEntry[] }) => {
    mockCharactersBand(props);
    return <div data-testid="characters-band-stub" />;
  },
}));

const mockAttentionBand = vi.fn();
vi.mock('../hall/AttentionBand', () => ({
  AttentionBand: (props: { characters: MyRosterEntry[] }) => {
    mockAttentionBand(props);
    return <div data-testid="attention-band-stub" />;
  },
}));

const mockOffscreenActsPlate = vi.fn();
vi.mock('../hall/OffscreenActsPlate', () => ({
  OffscreenActsPlate: (props: { characters: MyRosterEntry[] }) => {
    mockOffscreenActsPlate(props);
    return <div data-testid="offscreen-acts-plate-stub" />;
  },
}));

vi.mock('../hall/WorldBand', () => ({
  WorldBand: () => <div data-testid="world-band-stub" />,
}));

const aria: MyRosterEntry = {
  id: 1,
  name: 'Aria',
  character_id: 42,
  profile_picture_url: null,
  primary_persona_id: 7,
  active_persona_id: 7,
  unread_narrative_count: 0,
  lifecycle_state: 'ALIVE',
  roster_type: 'Active',
  character_type: 'PC',
};

function gmAccount(overrides: Partial<AccountData> = {}): AccountData {
  return {
    id: 1,
    username: 'gmuser',
    display_name: 'GM User',
    last_login: null,
    email: 'gm@example.com',
    email_verified: true,
    can_create_characters: true,
    is_staff: false,
    is_gm: true,
    available_characters: [],
    pending_applications: [],
    selected_entry_id: null,
    selected_entry: null,
    ...overrides,
  };
}

describe('HallPage', () => {
  afterEach(() => {
    store.dispatch(setAccount(null));
  });

  it('renders a loading skeleton (not the zero-character remedy) while the roster query is loading (review fix)', () => {
    mockUseMyRosterEntriesQuery.mockReturnValue({ data: undefined, isLoading: true });
    renderWithProviders(<HallPage />);

    expect(screen.getByTestId('characters-loading-skeleton')).toBeInTheDocument();
    expect(screen.queryByTestId('welcome-panel-stub')).not.toBeInTheDocument();
    expect(screen.queryByTestId('characters-band-stub')).not.toBeInTheDocument();
  });

  it('renders the WelcomePanel remedy in place of the character grid for a zero-character account', () => {
    mockUseMyRosterEntriesQuery.mockReturnValue({ data: [] });
    renderWithProviders(<HallPage />);

    expect(screen.getByTestId('welcome-panel-stub')).toBeInTheDocument();
    expect(screen.queryByTestId('characters-band-stub')).not.toBeInTheDocument();
    // World/Attention bands still mount for a zero-character account.
    expect(screen.getByTestId('attention-band-stub')).toBeInTheDocument();
    expect(screen.getByTestId('world-band-stub')).toBeInTheDocument();
  });

  it('renders CharactersBand alongside the WelcomePanel remedy for a zero-character GM account (#3478 fix round)', () => {
    store.dispatch(setAccount(gmAccount({ is_gm: true, is_staff: false })));
    mockUseMyRosterEntriesQuery.mockReturnValue({ data: [] });
    renderWithProviders(<HallPage />);

    expect(screen.getByTestId('welcome-panel-stub')).toBeInTheDocument();
    expect(screen.getByTestId('characters-band-stub')).toBeInTheDocument();
    expect(mockCharactersBand).toHaveBeenCalledWith(expect.objectContaining({ characters: [] }));
  });

  it('renders CharactersBand alongside the WelcomePanel remedy for a zero-character staff account (#3478 fix round)', () => {
    store.dispatch(setAccount(gmAccount({ is_gm: false, is_staff: true })));
    mockUseMyRosterEntriesQuery.mockReturnValue({ data: [] });
    renderWithProviders(<HallPage />);

    expect(screen.getByTestId('welcome-panel-stub')).toBeInTheDocument();
    expect(screen.getByTestId('characters-band-stub')).toBeInTheDocument();
  });

  it('renders CharactersBand (not the WelcomePanel remedy) once the account has characters', () => {
    mockUseMyRosterEntriesQuery.mockReturnValue({ data: [aria] });
    renderWithProviders(<HallPage />);

    expect(screen.getByTestId('characters-band-stub')).toBeInTheDocument();
    expect(screen.queryByTestId('welcome-panel-stub')).not.toBeInTheDocument();
    expect(mockCharactersBand).toHaveBeenCalledWith(
      expect.objectContaining({ characters: [aria] })
    );
    expect(mockAttentionBand).toHaveBeenCalledWith(expect.objectContaining({ characters: [aria] }));
  });

  it('mounts all three bands for a normal (non-zero-character) account', () => {
    mockUseMyRosterEntriesQuery.mockReturnValue({ data: [aria] });
    renderWithProviders(<HallPage />);

    expect(screen.getByTestId('characters-band-stub')).toBeInTheDocument();
    expect(screen.getByTestId('attention-band-stub')).toBeInTheDocument();
    expect(screen.getByTestId('world-band-stub')).toBeInTheDocument();
  });

  it('mounts the OffscreenActsPlate with the same characters list', () => {
    mockUseMyRosterEntriesQuery.mockReturnValue({ data: [aria] });
    renderWithProviders(<HallPage />);

    expect(screen.getByTestId('offscreen-acts-plate-stub')).toBeInTheDocument();
    expect(mockOffscreenActsPlate).toHaveBeenCalledWith(
      expect.objectContaining({ characters: [aria] })
    );
  });
});

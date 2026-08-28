/**
 * HallPage tests (#3412 slice 2) — composition/wiring only. Band internals
 * (CharactersBand/AttentionBand/WorldBand) have their own test suites under
 * `hall/__tests__/`; this file verifies the zero-character remedy swap and
 * that every band mounts with the right data.
 */
import { screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { HallPage } from '../HallPage';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import type { MyRosterEntry } from '@/roster/types';

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
};

describe('HallPage', () => {
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

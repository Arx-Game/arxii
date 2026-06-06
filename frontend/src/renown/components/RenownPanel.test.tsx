import { screen } from '@testing-library/react';
import { vi } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { RenownPanel } from './RenownPanel';
import type { UseQueryResult } from '@tanstack/react-query';
import type { RenownPayload, RenownEligiblePersona } from '../types';

vi.mock('../queries', () => ({
  useRenownEligiblePersonasQuery: vi.fn(),
  usePersonaRenownQuery: vi.fn(),
}));
import { useRenownEligiblePersonasQuery, usePersonaRenownQuery } from '../queries';

const mockPersonasQuery = vi.mocked(useRenownEligiblePersonasQuery);
const mockRenownQuery = vi.mocked(usePersonaRenownQuery);

function makeRenown(overrides: Partial<RenownPayload> = {}): RenownPayload {
  return {
    persona_id: 1,
    persona_name: 'Alice',
    prestige: { dwellings: 100, items: 50, orgs: 25, deeds: 75, total: 250 },
    fame: {
      points: 250,
      tier: 'talked_about',
      tier_label: 'Talked About',
      tier_multiplier: 1.25,
      next_tier: 'celebrity',
      next_tier_threshold: 1000,
    },
    reputation: [],
    recent_deeds: [],
    owned_dwellings: [],
    tenanted_rooms: [],
    ...overrides,
  };
}

function setPersonas(personas: RenownEligiblePersona[]) {
  mockPersonasQuery.mockReturnValue({
    data: personas,
    isLoading: false,
  } as unknown as UseQueryResult<RenownEligiblePersona[], Error>);
}

function setRenown(payload: RenownPayload | undefined, isLoading = false) {
  mockRenownQuery.mockReturnValue({
    data: payload,
    isLoading,
  } as unknown as UseQueryResult<RenownPayload, Error>);
}

describe('RenownPanel', () => {
  it('renders empty state when the sheet has no PRIMARY/ESTABLISHED personas', () => {
    setPersonas([]);
    setRenown(undefined);
    renderWithProviders(<RenownPanel characterSheetId={1} />);
    expect(screen.getByText(/no personas with renown/i)).toBeInTheDocument();
  });

  it('renders renown for the primary persona by default', () => {
    setPersonas([{ id: 1, name: 'Alice', persona_type: 'primary' }]);
    setRenown(makeRenown());
    renderWithProviders(<RenownPanel characterSheetId={1} />);
    expect(screen.getByText('Talked About')).toBeInTheDocument();
    // total_prestige and fame.points both happen to be 250 in this
    // fixture; just confirm at least one element rendered that value.
    expect(screen.getAllByText(/250/).length).toBeGreaterThan(0);
  });

  it('shows tier multiplier in the fame card', () => {
    setPersonas([{ id: 1, name: 'Alice', persona_type: 'primary' }]);
    setRenown(makeRenown());
    renderWithProviders(<RenownPanel characterSheetId={1} />);
    expect(screen.getByText(/×1.25 prestige/)).toBeInTheDocument();
  });

  it('shows persona selector tabs when there are multiple eligible personas', () => {
    setPersonas([
      { id: 1, name: 'Alice', persona_type: 'primary' },
      { id: 2, name: 'Bob the Stranger', persona_type: 'established' },
    ]);
    setRenown(makeRenown());
    renderWithProviders(<RenownPanel characterSheetId={1} />);
    expect(screen.getByRole('tab', { name: 'Alice' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Bob the Stranger' })).toBeInTheDocument();
  });

  it('hides the persona selector when only one persona qualifies', () => {
    setPersonas([{ id: 1, name: 'Alice', persona_type: 'primary' }]);
    setRenown(makeRenown());
    renderWithProviders(<RenownPanel characterSheetId={1} />);
    expect(screen.queryByRole('tab', { name: 'Alice' })).not.toBeInTheDocument();
  });

  it('renders reputation entries with named tier labels (no raw numbers)', () => {
    setPersonas([{ id: 1, name: 'Alice', persona_type: 'primary' }]);
    setRenown(
      makeRenown({
        reputation: [
          { society_id: 1, society_name: 'House of the Sword', tier: 'liked' },
          { society_id: 2, society_name: 'Order of the Quill', tier: 'reviled' },
        ],
      })
    );
    renderWithProviders(<RenownPanel characterSheetId={1} />);
    expect(screen.getByText('House of the Sword')).toBeInTheDocument();
    expect(screen.getByText('Liked')).toBeInTheDocument();
    expect(screen.getByText('Reviled')).toBeInTheDocument();
  });

  it('renders deeds log with title + date', () => {
    setPersonas([{ id: 1, name: 'Alice', persona_type: 'primary' }]);
    setRenown(
      makeRenown({
        recent_deeds: [
          { id: 1, title: 'Saved the village', base_value: 50, created_at: '2026-01-15T00:00:00Z' },
        ],
      })
    );
    renderWithProviders(<RenownPanel characterSheetId={1} />);
    expect(screen.getByText('Saved the village')).toBeInTheDocument();
  });

  it('shows empty deeds message when none exist', () => {
    setPersonas([{ id: 1, name: 'Alice', persona_type: 'primary' }]);
    setRenown(makeRenown());
    renderWithProviders(<RenownPanel characterSheetId={1} />);
    expect(screen.getByText(/no deeds recorded yet/i)).toBeInTheDocument();
  });
});

import { screen } from '@testing-library/react';
import { vi } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { RenownCardPanel } from './RenownCardPanel';
import type { UseQueryResult } from '@tanstack/react-query';
import type { RenownCardPayload, RenownEligiblePersona } from '../types';

vi.mock('../queries', () => ({
  useRenownEligiblePersonasQuery: vi.fn(),
  usePersonaRenownCardQuery: vi.fn(),
}));
import { useRenownEligiblePersonasQuery, usePersonaRenownCardQuery } from '../queries';

const mockPersonasQuery = vi.mocked(useRenownEligiblePersonasQuery);
const mockCardQuery = vi.mocked(usePersonaRenownCardQuery);

function makeCard(overrides: Partial<RenownCardPayload> = {}): RenownCardPayload {
  return {
    persona_id: 1,
    persona_name: 'Alice',
    fame: { tier: 'celebrity', tier_label: 'Celebrity' },
    visible_deeds: [],
    visible_reputation: [],
    ...overrides,
  };
}

function setPersonas(personas: RenownEligiblePersona[]) {
  mockPersonasQuery.mockReturnValue({
    data: personas,
    isLoading: false,
  } as unknown as UseQueryResult<RenownEligiblePersona[], Error>);
}

function setCard(payload: RenownCardPayload | undefined, isLoading = false) {
  mockCardQuery.mockReturnValue({
    data: payload,
    isLoading,
  } as unknown as UseQueryResult<RenownCardPayload, Error>);
}

describe('RenownCardPanel', () => {
  it('renders empty state when target has no eligible personas', () => {
    setPersonas([]);
    setCard(undefined);
    renderWithProviders(<RenownCardPanel characterSheetId={1} viewerPersonaId={5} />);
    expect(screen.getByText(/no personas with renown/i)).toBeInTheDocument();
  });

  it('shows the tier label only (no numeric reveal)', () => {
    setPersonas([{ id: 1, name: 'Alice', persona_type: 'primary' }]);
    setCard(makeCard());
    renderWithProviders(<RenownCardPanel characterSheetId={1} viewerPersonaId={5} />);
    expect(screen.getByText('Celebrity')).toBeInTheDocument();
    expect(screen.getByText(/As your circles read them/)).toBeInTheDocument();
  });

  it('renders visible deeds when present', () => {
    setPersonas([{ id: 1, name: 'Alice', persona_type: 'primary' }]);
    setCard(
      makeCard({
        visible_deeds: [
          {
            id: 1,
            title: 'Heard at court',
            base_value: 30,
            created_at: '2026-01-15T00:00:00Z',
          },
        ],
      })
    );
    renderWithProviders(<RenownCardPanel characterSheetId={1} viewerPersonaId={5} />);
    expect(screen.getByText('Heard at court')).toBeInTheDocument();
  });

  it('renders visible reputation rows', () => {
    setPersonas([{ id: 1, name: 'Alice', persona_type: 'primary' }]);
    setCard(
      makeCard({
        visible_reputation: [{ society_id: 1, society_name: 'House Viewer', tier: 'liked' }],
      })
    );
    renderWithProviders(<RenownCardPanel characterSheetId={1} viewerPersonaId={5} />);
    expect(screen.getByText('House Viewer')).toBeInTheDocument();
    expect(screen.getByText('Liked')).toBeInTheDocument();
  });

  it('shows empty deed message when nothing is visible (cloaked persona)', () => {
    setPersonas([{ id: 1, name: 'Cloaked', persona_type: 'primary' }]);
    setCard(makeCard({ persona_name: 'Cloaked' }));
    renderWithProviders(<RenownCardPanel characterSheetId={1} viewerPersonaId={5} />);
    expect(screen.getByText(/no deeds recorded yet/i)).toBeInTheDocument();
  });

  it('passes viewerPersonaId through to the query', () => {
    setPersonas([{ id: 1, name: 'Alice', persona_type: 'primary' }]);
    setCard(makeCard());
    renderWithProviders(<RenownCardPanel characterSheetId={1} viewerPersonaId={42} />);
    expect(mockCardQuery).toHaveBeenCalledWith(1, 42);
  });

  it('accepts null viewerPersonaId for anonymous viewer', () => {
    setPersonas([{ id: 1, name: 'Alice', persona_type: 'primary' }]);
    setCard(makeCard());
    renderWithProviders(<RenownCardPanel characterSheetId={1} viewerPersonaId={null} />);
    expect(mockCardQuery).toHaveBeenCalledWith(1, null);
  });
});

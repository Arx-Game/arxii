import { screen } from '@testing-library/react';
import { vi } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { ReputationTab } from './ReputationTab';
import type { UseQueryResult } from '@tanstack/react-query';
import type { RenownPayload, RenownCardPayload, RenownEligiblePersona } from '@/renown/types';
import type { PersonaHeatRow } from '@/justice/api';
import type { OrganizationReputation, OrganizationMembership } from '../api';
import type { CharacterCovenantRole } from '@/covenants/api';

vi.mock('@/renown/queries', () => ({
  useRenownEligiblePersonasQuery: vi.fn(),
  usePersonaRenownQuery: vi.fn(),
  usePersonaRenownCardQuery: vi.fn(),
}));
vi.mock('@/justice/queries', () => ({
  usePersonaHeat: vi.fn(),
}));
vi.mock('../queries', () => ({
  useOrganizationMembershipsQuery: vi.fn(),
  useOrganizationReputationsQuery: vi.fn(),
  useCovenantRolesQuery: vi.fn(),
}));

import {
  useRenownEligiblePersonasQuery,
  usePersonaRenownQuery,
  usePersonaRenownCardQuery,
} from '@/renown/queries';
import { usePersonaHeat } from '@/justice/queries';
import {
  useOrganizationMembershipsQuery,
  useOrganizationReputationsQuery,
  useCovenantRolesQuery,
} from '../queries';

const mockPersonasQuery = vi.mocked(useRenownEligiblePersonasQuery);
const mockRenownQuery = vi.mocked(usePersonaRenownQuery);
const mockRenownCardQuery = vi.mocked(usePersonaRenownCardQuery);
const mockHeatQuery = vi.mocked(usePersonaHeat);
const mockMembershipsQuery = vi.mocked(useOrganizationMembershipsQuery);
const mockReputationsQuery = vi.mocked(useOrganizationReputationsQuery);
const mockCovenantRolesQuery = vi.mocked(useCovenantRolesQuery);

function makeRenown(overrides: Partial<RenownPayload> = {}): RenownPayload {
  return {
    persona_id: 1,
    persona_name: 'Alice',
    prestige: { dwellings: 0, items: 0, orgs: 0, deeds: 0, fashion: 0, total: 0 },
    fame: {
      points: 0,
      tier: 'unknown',
      tier_label: 'Unknown',
      tier_multiplier: 1,
      next_tier: null,
      next_tier_threshold: null,
    },
    reputation: [],
    recent_deeds: [],
    owned_dwellings: [],
    tenanted_rooms: [],
    ...overrides,
  } as RenownPayload;
}

function makeCard(overrides: Partial<RenownCardPayload> = {}): RenownCardPayload {
  return {
    persona_id: 1,
    persona_name: 'Alice',
    fame: { tier: 'unknown', tier_label: 'Unknown' },
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

function setRenown(payload: RenownPayload | undefined) {
  mockRenownQuery.mockReturnValue({
    data: payload,
    isLoading: false,
  } as unknown as UseQueryResult<RenownPayload, Error>);
}

function setCard(payload: RenownCardPayload | undefined) {
  mockRenownCardQuery.mockReturnValue({
    data: payload,
    isLoading: false,
  } as unknown as UseQueryResult<RenownCardPayload, Error>);
}

function setHeat(rows: PersonaHeatRow[]) {
  mockHeatQuery.mockReturnValue({
    data: rows,
    isLoading: false,
  } as unknown as UseQueryResult<PersonaHeatRow[], Error>);
}

function setMemberships(rows: OrganizationMembership[]) {
  mockMembershipsQuery.mockReturnValue({
    data: rows,
    isLoading: false,
  } as unknown as UseQueryResult<OrganizationMembership[], Error>);
}

function setReputations(rows: OrganizationReputation[]) {
  mockReputationsQuery.mockReturnValue({
    data: rows,
    isLoading: false,
  } as unknown as UseQueryResult<OrganizationReputation[], Error>);
}

function setCovenantRoles(rows: CharacterCovenantRole[]) {
  mockCovenantRolesQuery.mockReturnValue({
    data: rows,
    isLoading: false,
  } as unknown as UseQueryResult<CharacterCovenantRole[], Error>);
}

describe('ReputationTab', () => {
  beforeEach(() => {
    setPersonas([{ id: 1, name: 'Alice', persona_type: 'primary' }]);
    setMemberships([]);
    setReputations([]);
    setCovenantRoles([]);
    setHeat([]);
  });

  it('renders Renown, Standing, and Covenants sections for the own view', () => {
    setRenown(makeRenown());
    renderWithProviders(
      <ReputationTab entryCharacterId={1} viewerPersonaId={1} isMyCharacter viewerEntryId={1} />
    );
    expect(screen.getByText('Renown')).toBeInTheDocument();
    expect(screen.getByText('Standing')).toBeInTheDocument();
    expect(screen.getByText('Covenants')).toBeInTheDocument();
  });

  it('shows a Wanted badge on a society row whose id appears in the heat data', () => {
    setRenown(
      makeRenown({
        reputation: [{ society_id: 3, society_name: 'The Honest', tier: 'disliked' }],
      })
    );
    setHeat([
      {
        id: 1,
        area_name: 'The Ward',
        society: 3,
        society_name: 'The Honest',
        tier: 'heat_is_on',
        tier_label: 'Heat Is On',
        alleged_deeds: [],
      },
    ]);
    renderWithProviders(
      <ReputationTab entryCharacterId={1} viewerPersonaId={1} isMyCharacter viewerEntryId={1} />
    );
    expect(screen.getByText('Wanted')).toBeInTheDocument();
  });

  it('renders only RenownCardPanel for a foreign view — no Standing/Covenants/Wanted', () => {
    setCard(makeCard());
    renderWithProviders(
      <ReputationTab
        entryCharacterId={1}
        viewerPersonaId={5}
        isMyCharacter={false}
        viewerEntryId={null}
      />
    );
    expect(screen.queryByText('Standing')).not.toBeInTheDocument();
    expect(screen.queryByText('Covenants')).not.toBeInTheDocument();
    expect(screen.queryByText('Wanted')).not.toBeInTheDocument();
  });
});

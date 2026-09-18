import { screen } from '@testing-library/react';
import { vi } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { ReputationTab, CovenantRoles } from './ReputationTab';
import type { UseQueryResult } from '@tanstack/react-query';
import type { RenownPayload, RenownCardPayload, RenownEligiblePersona } from '@/renown/types';
import type { PersonaHeatRow } from '@/justice/api';
import type { CharacterSheetStanding } from '@/character_sheets/api';

vi.mock('@/renown/queries', () => ({
  useRenownEligiblePersonasQuery: vi.fn(),
  usePersonaRenownQuery: vi.fn(),
  usePersonaRenownCardQuery: vi.fn(),
}));
vi.mock('@/justice/queries', () => ({
  usePersonaHeat: vi.fn(),
}));

import {
  useRenownEligiblePersonasQuery,
  usePersonaRenownQuery,
  usePersonaRenownCardQuery,
} from '@/renown/queries';
import { usePersonaHeat } from '@/justice/queries';

const mockPersonasQuery = vi.mocked(useRenownEligiblePersonasQuery);
const mockRenownQuery = vi.mocked(usePersonaRenownQuery);
const mockRenownCardQuery = vi.mocked(usePersonaRenownCardQuery);
const mockHeatQuery = vi.mocked(usePersonaHeat);

const NO_STANDING: CharacterSheetStanding = { memberships: [], reputations: [] };

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

describe('ReputationTab', () => {
  beforeEach(() => {
    setPersonas([{ id: 1, name: 'Alice', persona_type: 'primary' }]);
    setHeat([]);
  });

  it('renders Renown and the standing groups for the own view', () => {
    setRenown(makeRenown());
    renderWithProviders(
      <ReputationTab
        entryCharacterId={1}
        viewerPersonaId={1}
        isMyCharacter
        viewedEntryId={1}
        standing={NO_STANDING}
      />
    );
    expect(screen.getByText('Renown')).toBeInTheDocument();
    // "Standing" is the section heading the SHEET draws above this panel (#3898); the
    // panel's own groups name what they hold instead.
    expect(screen.getByText('Belongs to')).toBeInTheDocument();
    expect(screen.getByText('Thought of as')).toBeInTheDocument();
    // Covenant is its own rail block on the sheet (#3898), not a group in here.
    expect(screen.queryByText('Covenants')).not.toBeInTheDocument();
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
        area: 1,
        area_name: 'The Ward',
        society: 3,
        society_name: 'The Honest',
        tier: 'heat_is_on',
        tier_label: 'Heat Is On',
        alleged_deeds: [],
      },
    ]);
    renderWithProviders(
      <ReputationTab
        entryCharacterId={1}
        viewerPersonaId={1}
        isMyCharacter
        viewedEntryId={1}
        standing={NO_STANDING}
      />
    );
    expect(screen.getByText('Wanted')).toBeInTheDocument();
  });

  it('renders the standing payload on a foreign view, with the renown CARD, not the panel', () => {
    // #3906: standing is friends-visible, so the server decides — a foreign viewer the
    // server allowed gets the same rows. The wanted flag stays the owner's alone.
    setCard(makeCard());
    renderWithProviders(
      <ReputationTab
        entryCharacterId={1}
        viewerPersonaId={5}
        isMyCharacter={false}
        viewedEntryId={null}
        standing={{
          memberships: [{ organization_id: 10, organization: 'House Valardin', title: 'Voice' }],
          reputations: [{ organization_id: 20, organization: 'The Iron Guard', tier: 'liked' }],
        }}
      />
    );
    expect(screen.getByText('House Valardin')).toBeInTheDocument();
    expect(screen.getByText('The Iron Guard')).toBeInTheDocument();
    expect(screen.queryByText('Wanted')).not.toBeInTheDocument();
  });

  it('says so in the world voice when the server withheld or emptied standing', () => {
    setRenown(makeRenown());
    renderWithProviders(
      <ReputationTab
        entryCharacterId={1}
        viewerPersonaId={1}
        isMyCharacter
        viewedEntryId={1}
        standing={NO_STANDING}
      />
    );
    expect(screen.getByText('They belong to nobody.')).toBeInTheDocument();
    expect(screen.getByText('No organization has an opinion of them yet.')).toBeInTheDocument();
  });

  it('does not render the account-wide society-reputation list twice (only via RenownPanel)', () => {
    setRenown(
      makeRenown({
        reputation: [{ society_id: 3, society_name: 'The Honest', tier: 'disliked' }],
      })
    );
    renderWithProviders(
      <ReputationTab
        entryCharacterId={1}
        viewerPersonaId={1}
        isMyCharacter
        viewedEntryId={1}
        standing={NO_STANDING}
      />
    );
    // "The Honest" comes from RenownPanel's own reputation card; it must appear exactly
    // once — the Standing card no longer renders a second, duplicate reputation list.
    expect(screen.getAllByText('The Honest')).toHaveLength(1);
  });
});

describe('CovenantRoles', () => {
  it('draws each role from the sheet payload, flagging the engaged one', () => {
    renderWithProviders(
      <CovenantRoles
        covenants={[
          {
            id: 1,
            covenant_id: 7,
            covenant: 'The Quiet Hand',
            role: 'Blade',
            rank: 'Sworn',
            engaged: true,
          },
          {
            id: 2,
            covenant_id: 8,
            covenant: 'The Long Watch',
            role: 'Scribe',
            rank: 'Novice',
            engaged: false,
          },
        ]}
      />
    );
    expect(screen.getByText('Blade')).toBeInTheDocument();
    expect(screen.getByText('Scribe')).toBeInTheDocument();
    expect(screen.getAllByText('Engaged')).toHaveLength(1);
  });

  it('says they hold none rather than drawing an empty block', () => {
    renderWithProviders(<CovenantRoles covenants={[]} />);
    expect(screen.getByText('They hold no covenant role.')).toBeInTheDocument();
  });
});

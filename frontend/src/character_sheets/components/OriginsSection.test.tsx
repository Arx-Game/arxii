/**
 * OriginsSection tests (#3660).
 *
 * Covers: one card per `kind === 'group'` row (name/link, tie + stage badges, tier badge),
 * the person rows scoped to that card's organization, blank `figure_name` hiding the person
 * for a foreign viewer, an unresolved (`organization_id: null`) card falling back to the slot
 * name and never collecting unanchored person rows, and the prose rendered after the cards.
 */

import { screen } from '@testing-library/react';
import { vi } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { OriginsSection } from './OriginsSection';
import type { CharacterSheetStory } from '@/character_sheets/api';
import type { OrganizationReputation } from '@/reputation/api';

vi.mock('@/reputation/queries', () => ({
  useOrganizationReputationsQuery: vi.fn(),
}));

import { useOrganizationReputationsQuery } from '@/reputation/queries';

const mockReputationsQuery = vi.mocked(useOrganizationReputationsQuery);

function makeStory(): CharacterSheetStory {
  return {
    background: 'Raised in the shadow of the guild hall.',
    origin_story_state: 'complete',
    origin_slots: [
      {
        slot_id: 1,
        slot_name: 'Who raised you?',
        slot_prompt: 'Who raised you?',
        value: 'They took me in off the docks.',
        kind: 'group',
        connection_kind: 'raised_by',
        life_stage: 'childhood',
        choice_name: 'The Merchants Guild',
        choice_description: 'A trading house with fingers in every port.',
        organization_id: 5,
        organization_name: "Merchants' Guild",
        figure_name: '',
      },
      {
        slot_id: 2,
        slot_name: 'Who did you serve?',
        slot_prompt: 'Who did you serve?',
        value: '',
        kind: 'group',
        connection_kind: 'served',
        life_stage: '',
        choice_name: '',
        choice_description: '',
        organization_id: null,
        // The serializer guarantees organization_name is "" whenever organization_id is
        // null (#3660 review) - an unresolved anchor is a reachable backend state (e.g. an
        // unresolved own-family/served-house question), and the card falls back to slot_name.
        organization_name: '',
        figure_name: '',
      },
      {
        slot_id: 3,
        slot_name: 'Who taught you?',
        slot_prompt: 'Who taught you?',
        value: 'She never let me forget a knot.',
        kind: 'person',
        connection_kind: 'taught_by',
        life_stage: 'youth',
        choice_name: '',
        choice_description: '',
        organization_id: 5,
        organization_name: "Merchants' Guild",
        figure_name: 'Old Mira',
      },
      {
        slot_id: 4,
        slot_name: 'What do you believe?',
        slot_prompt: 'What do you believe?',
        value: 'Coin over blood.',
        kind: 'text',
        connection_kind: '',
        life_stage: '',
        choice_name: '',
        choice_description: '',
        organization_id: null,
        organization_name: '',
        figure_name: '',
      },
    ],
  };
}

function makeRep(overrides: Partial<OrganizationReputation> = {}): OrganizationReputation {
  return {
    id: 1,
    persona: 1,
    organization: 5,
    organization_name: "Merchants' Guild",
    tier: 'liked',
    ...overrides,
  };
}

describe('OriginsSection', () => {
  beforeEach(() => {
    mockReputationsQuery.mockReturnValue({
      data: undefined,
    } as unknown as ReturnType<typeof useOrganizationReputationsQuery>);
  });

  it('renders a card per group row with the group name, tie and stage badges', () => {
    renderWithProviders(
      <OriginsSection story={makeStory()} background={makeStory().background} isMyCharacter />
    );

    expect(screen.getByText('Origins')).toBeInTheDocument();
    const guildLink = screen.getByRole('link', { name: "Merchants' Guild" });
    expect(guildLink).toHaveAttribute('href', '/orgs/5');
    expect(screen.getByText('Raised by')).toBeInTheDocument();
    expect(screen.getByText('Childhood')).toBeInTheDocument();
    // The unresolved-organization row has no id to link to, no org name to show, and a
    // blank stage badge - its card title falls back to the slot's own name.
    expect(screen.getByText('Who did you serve?')).toBeInTheDocument();
    expect(screen.getByText('Served')).toBeInTheDocument();
  });

  it('shows a tier badge for the own sheet when a reputation row matches the organization', () => {
    mockReputationsQuery.mockReturnValue({
      data: [makeRep()],
    } as unknown as ReturnType<typeof useOrganizationReputationsQuery>);
    renderWithProviders(
      <OriginsSection story={makeStory()} background={makeStory().background} isMyCharacter />
    );

    expect(screen.getByText('Liked')).toBeInTheDocument();
  });

  it("shows the named figure and their answer for the own sheet, and the group's choice", () => {
    renderWithProviders(
      <OriginsSection story={makeStory()} background={makeStory().background} isMyCharacter />
    );

    expect(screen.getByText('Old Mira')).toBeInTheDocument();
    expect(screen.getByText(/She never let me forget a knot/)).toBeInTheDocument();
    expect(screen.getByText('The Merchants Guild')).toBeInTheDocument();
    expect(screen.getByText('A trading house with fingers in every port.')).toBeInTheDocument();
  });

  it('hides the named figure for a foreign viewer once figure_name is blanked', () => {
    const story = makeStory();
    story.origin_slots = story.origin_slots.map((row) =>
      row.kind === 'person' ? { ...row, figure_name: '' } : row
    );
    renderWithProviders(
      <OriginsSection story={story} background={story.background} isMyCharacter={false} />
    );

    expect(screen.queryByText('Old Mira')).not.toBeInTheDocument();
  });

  it('never attaches an unanchored person row to an unresolved (null-organization) card', () => {
    const story = makeStory();
    story.origin_slots = [
      ...story.origin_slots,
      {
        slot_id: 6,
        slot_name: 'Who else did you know?',
        slot_prompt: 'Who else did you know?',
        value: 'We never spoke of home.',
        kind: 'person',
        connection_kind: 'sailed_with',
        life_stage: 'youth',
        choice_name: '',
        choice_description: '',
        organization_id: null,
        organization_name: '',
        figure_name: 'Quiet Ansel',
      },
    ];
    renderWithProviders(
      <OriginsSection story={story} background={story.background} isMyCharacter />
    );

    // The unanchored person shares organization_id: null with the unresolved "Who did you
    // serve?" card; a naive `===` match would attach it there. It must appear nowhere.
    expect(screen.queryByText('Quiet Ansel')).not.toBeInTheDocument();
  });

  it('renders the prose after the cards, and never renders text/pick rows as cards', () => {
    renderWithProviders(
      <OriginsSection
        story={makeStory()}
        background="Raised in the shadow of the guild hall."
        isMyCharacter
      />
    );

    expect(screen.getByText('Raised in the shadow of the guild hall.')).toBeInTheDocument();
    expect(screen.queryByText('Coin over blood.')).not.toBeInTheDocument();
  });
});

/**
 * SpellbookTab tests (#1446) — magic spellbook/status view: gifts, techniques, motif, aura,
 * and own-view workbench link-outs.
 *
 * The server already gates `payload.magic` to null for foreign viewers without visibility
 * AND for magic-less characters (`_build_magic`, src/world/character_sheets/serializers.py) —
 * this component only renders whatever `useCharacterSheetQuery` returns.
 */

import { screen } from '@testing-library/react';
import { vi } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { SpellbookTab } from './SpellbookTab';
import type { CharacterSheetPayload, CharacterSheetMagic } from '@/character_sheets/api';

vi.mock('@/character_sheets/queries', () => ({
  useCharacterSheetQuery: vi.fn(),
}));

import * as queries from '@/character_sheets/queries';

function mockPayload(magic: CharacterSheetMagic | null | undefined, isLoading = false) {
  vi.mocked(queries.useCharacterSheetQuery).mockReturnValue({
    data: magic === undefined ? undefined : ({ magic } as CharacterSheetPayload),
    isLoading,
  } as unknown as ReturnType<typeof queries.useCharacterSheetQuery>);
}

function makeMagic(overrides: Partial<CharacterSheetMagic> = {}): CharacterSheetMagic {
  return {
    gifts: [
      {
        name: 'Pyromancy',
        description: 'Command over flame.',
        resonances: ['Ember'],
        techniques: [
          {
            name: 'Flare',
            level: 3,
            style: 'Manifestation',
            description: 'A burst of fire.',
          },
        ],
      },
    ],
    motif: {
      description: 'Smoke and cinders.',
      resonances: [{ name: 'Ember', facets: ['Fire', 'Ash'] }],
    },
    anima_ritual: null,
    aura: {
      celestial: 10,
      primal: 70,
      abyssal: 20,
      glimpse_story: 'A candle guttered and did not go out.',
    },
    ...overrides,
  };
}

describe('SpellbookTab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows a spinner while loading', () => {
    mockPayload(undefined, true);
    const { container } = renderWithProviders(
      <SpellbookTab characterId={1} isMyCharacter={false} />
    );
    expect(container.querySelector('.animate-spin')).toBeInTheDocument();
  });

  it('shows the muted empty line when magic is null', () => {
    mockPayload(null);
    renderWithProviders(<SpellbookTab characterId={1} isMyCharacter={false} />);
    expect(screen.getByText('Nothing is known of their magic.')).toBeInTheDocument();
  });

  it('renders the gift, its technique, the motif, and the aura', () => {
    mockPayload(makeMagic());
    renderWithProviders(<SpellbookTab characterId={1} isMyCharacter={false} />);

    expect(screen.getByText('Pyromancy')).toBeInTheDocument();
    expect(screen.getByText('Flare')).toBeInTheDocument();
    expect(screen.getByText('Smoke and cinders.')).toBeInTheDocument();
    expect(screen.getByText('A candle guttered and did not go out.')).toBeInTheDocument();
    // Aura is qualitative — no raw decimal percentages anywhere in the DOM.
    expect(screen.queryByText(/70/)).not.toBeInTheDocument();
  });

  it('does not render workbench links for a foreign viewer', () => {
    mockPayload(makeMagic());
    renderWithProviders(<SpellbookTab characterId={1} isMyCharacter={false} />);
    expect(screen.queryByRole('link', { name: /progression/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /threads/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /sanctums/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /rituals/i })).not.toBeInTheDocument();
  });

  it('renders workbench links for the own view', () => {
    mockPayload(makeMagic());
    renderWithProviders(<SpellbookTab characterId={1} isMyCharacter={true} />);

    expect(screen.getByRole('link', { name: /progression/i })).toHaveAttribute(
      'href',
      '/magic/progression'
    );
    expect(screen.getByRole('link', { name: /threads/i })).toHaveAttribute('href', '/threads');
    expect(screen.getByRole('link', { name: /sanctums/i })).toHaveAttribute('href', '/sanctums');
    expect(screen.getByRole('link', { name: /rituals/i })).toHaveAttribute('href', '/rituals');
  });
});

/**
 * SpellbookTab tests (#1446) — magic spellbook/status view: gifts, techniques, motif, aura,
 * and own-view workbench link-outs.
 *
 * The server already gates `payload.magic` to null for foreign viewers without visibility
 * AND for magic-less characters (`_build_magic`, src/world/character_sheets/serializers.py) —
 * this component only renders whatever `useCharacterSheetQuery` returns.
 *
 * Glimpse "finish later" coverage (#2427 Task 6): the finish-button affordance matrix, the
 * glimpse tag chips, and a dialog-interaction smoke test (GlimpseEditorDialog mounted, mutations
 * mocked) live at the bottom of this file.
 */

import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { SpellbookTab } from './SpellbookTab';
import type {
  CharacterSheetPayload,
  CharacterSheetMagic,
  CharacterSheetAura,
  CharacterSheetDistinction,
} from '@/character_sheets/api';
import type { GlimpseTagOption } from './glimpse/glimpseTypes';

vi.mock('@/character_sheets/queries', () => ({
  useCharacterSheetQuery: vi.fn(),
}));

// MotifStylePanel (#2030) is mounted below the Motif card for the own view —
// mock its hooks so this suite stays focused on SpellbookTab's own rendering
// and never issues a real fetch. GlimpseEditorDialog's mutations (#2427) are
// mocked here too, for the same reason.
vi.mock('@/magic/queries', () => ({
  useMotifStyleBindings: vi.fn(),
  useStyleCatalog: vi.fn(),
  useCharacterResonances: vi.fn(),
  useBindMotifStyle: vi.fn(),
  useUnbindMotifStyle: vi.fn(),
  useSetGlimpseTags: vi.fn(),
  useSetGlimpseProse: vi.fn(),
  useToggleGlimpseDistinction: vi.fn(),
}));

// GlimpseEditorDialog reads the catalog via the character-creation module's
// useGlimpseTags — mock it too so opening the dialog never issues a real fetch.
vi.mock('@/character-creation/queries', () => ({
  useGlimpseTags: vi.fn(),
}));

import * as queries from '@/character_sheets/queries';
import * as magicQueries from '@/magic/queries';
import * as cgQueries from '@/character-creation/queries';

function mockMotifStyleQueries() {
  vi.mocked(magicQueries.useMotifStyleBindings).mockReturnValue({
    data: { bindings: [] },
    isLoading: false,
  } as unknown as ReturnType<typeof magicQueries.useMotifStyleBindings>);
  vi.mocked(magicQueries.useStyleCatalog).mockReturnValue({
    data: { count: 0, next: null, previous: null, results: [] },
    isLoading: false,
  } as unknown as ReturnType<typeof magicQueries.useStyleCatalog>);
  vi.mocked(magicQueries.useCharacterResonances).mockReturnValue({
    data: [],
    isLoading: false,
  } as unknown as ReturnType<typeof magicQueries.useCharacterResonances>);
  vi.mocked(magicQueries.useBindMotifStyle).mockReturnValue({
    mutate: vi.fn(),
    isPending: false,
    isError: false,
    error: null,
  } as unknown as ReturnType<typeof magicQueries.useBindMotifStyle>);
  vi.mocked(magicQueries.useUnbindMotifStyle).mockReturnValue({
    mutate: vi.fn(),
    isPending: false,
    isError: false,
    error: null,
  } as unknown as ReturnType<typeof magicQueries.useUnbindMotifStyle>);
}

const glimpseTagCatalog: GlimpseTagOption[] = [
  {
    id: 1,
    axis: 'TONE',
    name: 'Wonder',
    slug: 'wonder',
    description: 'It felt like the world cracked open.',
    example: 'Everything glowed.',
    sort_order: 1,
    suggested_distinctions: [],
  },
  {
    id: 2,
    axis: 'TONE',
    name: 'Dread',
    slug: 'dread',
    description: 'It felt wrong from the first instant.',
    example: 'The air went cold.',
    sort_order: 2,
    suggested_distinctions: [],
  },
];

/** Mocks GlimpseEditorDialog's own hooks. Returns the mock functions for assertions. */
function mockGlimpseQueries() {
  const setTagsMutate = vi.fn();
  const setProseMutate = vi.fn();
  const toggleDistinction = vi.fn();

  vi.mocked(cgQueries.useGlimpseTags).mockReturnValue({
    data: glimpseTagCatalog,
    isLoading: false,
  } as unknown as ReturnType<typeof cgQueries.useGlimpseTags>);

  vi.mocked(magicQueries.useSetGlimpseTags).mockReturnValue({
    mutate: setTagsMutate,
    isPending: false,
  } as unknown as ReturnType<typeof magicQueries.useSetGlimpseTags>);

  vi.mocked(magicQueries.useSetGlimpseProse).mockReturnValue({
    mutate: setProseMutate,
    isPending: false,
  } as unknown as ReturnType<typeof magicQueries.useSetGlimpseProse>);

  vi.mocked(magicQueries.useToggleGlimpseDistinction).mockReturnValue({
    toggle: toggleDistinction,
    isPending: false,
  } as unknown as ReturnType<typeof magicQueries.useToggleGlimpseDistinction>);

  return { setTagsMutate, setProseMutate, toggleDistinction };
}

function mockPayload(
  magic: CharacterSheetMagic | null | undefined,
  options: { isLoading?: boolean; distinctions?: CharacterSheetDistinction[] } = {}
) {
  vi.mocked(queries.useCharacterSheetQuery).mockReturnValue({
    data:
      magic === undefined
        ? undefined
        : ({ magic, distinctions: options.distinctions ?? [] } as CharacterSheetPayload),
    isLoading: options.isLoading ?? false,
  } as unknown as ReturnType<typeof queries.useCharacterSheetQuery>);
}

function makeAura(overrides: Partial<CharacterSheetAura> = {}): CharacterSheetAura {
  return {
    id: 42,
    celestial: 10,
    primal: 70,
    abyssal: 20,
    glimpse_story: 'A candle guttered and did not go out.',
    glimpse_state: 'COMPLETE',
    glimpse_tags: [],
    can_finish_glimpse: false,
    ...overrides,
  };
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
      resonances: [{ name: 'Ember', facets: ['Fire', 'Ash'], styles: ['Sardonic'] }],
    },
    anima_ritual: null,
    aura: makeAura(),
    ...overrides,
  };
}

describe('SpellbookTab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockMotifStyleQueries();
    mockGlimpseQueries();
  });

  it('shows a spinner while loading', () => {
    mockPayload(undefined, { isLoading: true });
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
    expect(screen.getByText('Sardonic')).toBeInTheDocument();
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

  it('does not mount the style-binding panel for a foreign viewer', () => {
    mockPayload(makeMagic());
    renderWithProviders(<SpellbookTab characterId={1} isMyCharacter={false} />);
    expect(screen.queryByTestId('motif-style-panel')).not.toBeInTheDocument();
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

  it('mounts the style-binding panel for the own view', () => {
    mockPayload(makeMagic());
    renderWithProviders(<SpellbookTab characterId={1} isMyCharacter={true} />);
    expect(screen.getByTestId('motif-style-panel')).toBeInTheDocument();
  });

  // ---------------------------------------------------------------------
  // Glimpse chips + finish-button affordance matrix (#2427 Task 6)
  // ---------------------------------------------------------------------

  it('renders chosen glimpse tags as badge chips', () => {
    mockPayload(
      makeMagic({
        aura: makeAura({
          glimpse_tags: [
            { id: 1, axis: 'TONE', name: 'Wonder', description: 'It felt like magic.' },
          ],
        }),
      })
    );
    renderWithProviders(<SpellbookTab characterId={1} isMyCharacter={true} />);

    const chips = screen.getByTestId('spellbook-glimpse-tags');
    expect(chips).toHaveTextContent('Wonder');
  });

  it('does not render a glimpse-tags row when there are no chosen tags', () => {
    mockPayload(makeMagic({ aura: makeAura({ glimpse_tags: [] }) }));
    renderWithProviders(<SpellbookTab characterId={1} isMyCharacter={true} />);
    expect(screen.queryByTestId('spellbook-glimpse-tags')).not.toBeInTheDocument();
  });

  it('shows the finish-glimpse button for the owner when can_finish_glimpse is true', () => {
    mockPayload(
      makeMagic({ aura: makeAura({ can_finish_glimpse: true, glimpse_state: 'TAGS_ONLY' }) })
    );
    renderWithProviders(<SpellbookTab characterId={1} isMyCharacter={true} />);

    expect(screen.getByTestId('finish-glimpse-button')).toBeInTheDocument();
    expect(
      screen.getByText(/chosen the shape of it — write the story when ready/i)
    ).toBeInTheDocument();
  });

  it('omits the TAGS_ONLY prompt when the glimpse has not been started', () => {
    mockPayload(
      makeMagic({ aura: makeAura({ can_finish_glimpse: true, glimpse_state: 'NOT_STARTED' }) })
    );
    renderWithProviders(<SpellbookTab characterId={1} isMyCharacter={true} />);

    expect(screen.getByTestId('finish-glimpse-button')).toBeInTheDocument();
    expect(
      screen.queryByText(/chosen the shape of it — write the story when ready/i)
    ).not.toBeInTheDocument();
  });

  it('hides the finish-glimpse button once the glimpse is complete', () => {
    mockPayload(
      makeMagic({ aura: makeAura({ can_finish_glimpse: false, glimpse_state: 'COMPLETE' }) })
    );
    renderWithProviders(<SpellbookTab characterId={1} isMyCharacter={true} />);
    expect(screen.queryByTestId('finish-glimpse-button')).not.toBeInTheDocument();
  });

  it('hides the finish-glimpse button for a foreign viewer even when can_finish_glimpse is true', () => {
    // can_finish_glimpse is itself privileged/owner-only server-side, but the
    // component must not rely on that alone — it re-gates on isMyCharacter too.
    mockPayload(
      makeMagic({ aura: makeAura({ can_finish_glimpse: true, glimpse_state: 'TAGS_ONLY' }) })
    );
    renderWithProviders(<SpellbookTab characterId={1} isMyCharacter={false} />);
    expect(screen.queryByTestId('finish-glimpse-button')).not.toBeInTheDocument();
  });

  // ---------------------------------------------------------------------
  // Dialog interaction (#2427 Task 6) — mutations mocked, real GlimpseFlow.
  // ---------------------------------------------------------------------

  describe('GlimpseEditorDialog interaction', () => {
    function renderWithFinishableGlimpse() {
      mockPayload(
        makeMagic({
          aura: makeAura({
            can_finish_glimpse: true,
            glimpse_state: 'TAGS_ONLY',
            glimpse_tags: [
              { id: 1, axis: 'TONE', name: 'Wonder', description: 'It felt like magic.' },
            ],
          }),
        }),
        {
          distinctions: [
            {
              id: 7,
              name: 'Touched by the Unseen',
              rank: 1,
              notes: '',
              is_secret: false,
              is_from_glimpse: false,
            },
          ],
        }
      );
      return renderWithProviders(<SpellbookTab characterId={1} isMyCharacter={true} />);
    }

    it('opens seeded with the current prose and tag selection', async () => {
      renderWithFinishableGlimpse();
      await userEvent.click(screen.getByTestId('finish-glimpse-button'));

      const dialog = screen.getByTestId('glimpse-editor-dialog');
      expect(dialog).toBeInTheDocument();

      const storyField = screen.getByLabelText('Your Story') as HTMLTextAreaElement;
      expect(storyField.value).toBe('A candle guttered and did not go out.');

      // Save story starts disabled — the draft matches the last-saved prose.
      expect(screen.getByTestId('glimpse-save-story')).toBeDisabled();
    });

    it('fires useSetGlimpseTags when a different TONE tag is picked', async () => {
      const { setTagsMutate } = mockGlimpseQueries();
      renderWithFinishableGlimpse();
      await userEvent.click(screen.getByTestId('finish-glimpse-button'));

      await userEvent.click(screen.getByText('Dread'));

      expect(setTagsMutate).toHaveBeenCalledWith({ axis: 'TONE', tag_ids: [2] });
    });

    it('fires useSetGlimpseProse with the edited text when Save story is clicked', async () => {
      const { setProseMutate } = mockGlimpseQueries();
      renderWithFinishableGlimpse();
      await userEvent.click(screen.getByTestId('finish-glimpse-button'));

      const storyField = screen.getByLabelText('Your Story');
      await userEvent.clear(storyField);
      await userEvent.type(storyField, 'The world cracked open.');
      await userEvent.click(screen.getByTestId('glimpse-save-story'));

      expect(setProseMutate).toHaveBeenCalledWith({ text: 'The world cracked open.' });
    });

    it('toggles a distinction link via useToggleGlimpseDistinction', async () => {
      const { toggleDistinction } = mockGlimpseQueries();
      renderWithFinishableGlimpse();
      await userEvent.click(screen.getByTestId('finish-glimpse-button'));

      await userEvent.click(screen.getByText('Touched by the Unseen'));

      // is_from_glimpse was false for this CharacterDistinction (id 7) — toggling
      // it calls the link (not unlink) side.
      expect(toggleDistinction).toHaveBeenCalledWith(7, false);
    });
  });
});

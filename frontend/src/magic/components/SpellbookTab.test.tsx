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

import { act, render, screen, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Provider } from 'react-redux';
import { MemoryRouter } from 'react-router-dom';
import { store } from '@/store/store';
import userEvent from '@testing-library/user-event';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { vi } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { SpellbookTab } from './SpellbookTab';
import type {
  CharacterSheetPayload,
  CharacterSheetMagic,
  CharacterSheetAura,
  CharacterSheetDistinction,
  CharacterSheetTechnique,
  CharacterSheetStaffEdit,
} from '@/character_sheets/api';
import { StaffEditContext } from '@/character_sheets/components/sheet/staffEditContext';
import type { GlimpseTagOption } from './glimpse/glimpseTypes';
import type { TechniqueEffectSummary, TechniqueForm, TechniqueSignature } from '../types';

/** Minimal mock effect_summary (#2898). */
const mockEffectSummary: TechniqueEffectSummary = {
  relationship: 'enemy',
  hostile: false,
  target_type: 'single',
  reach: 'same',
  reach_hops: 0,
  arena: 'physical',
  anima_cost: 5,
  applies: [],
  removes: [],
  damage: [],
  treatments: [],
  grants: [],
  summary: 'Cast on an enemy, in melee range, in the physical arena. Costs 5 anima.',
  is_underspecified: false,
};

/** The base form every caster always has (#2901). */
const mockBaseForm: TechniqueForm = {
  variant_id: null,
  name: 'Flare',
  resonance_id: null,
  resonance_name: '',
  intensity: 6,
  control: 4,
  is_default: true,
  is_locked: false,
  unlock_thread_level: 0,
  thread_level: 0,
  is_early: false,
  effect_summary: mockEffectSummary,
};

vi.mock('@/character_sheets/queries', () => ({
  useCharacterSheetQuery: vi.fn(),
  // Staff edit mode's field (#4224) draws the Glimpse; only its save hook is reached.
  useStaffEditMutation: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useProfileTextVersions: vi.fn(() => ({ data: [] })),
  useRestoreProfileTextVersion: vi.fn(() => ({ mutate: vi.fn() })),
  useStaffChoiceOptions: vi.fn(() => ({ data: [] })),
}));

// MotifStylePanel (#2030) and TechniqueProgressPanel (#2739) are mounted below
// the Motif card for the own view — mock their hooks so this suite stays
// focused on SpellbookTab's own rendering and never issues a real fetch.
// GlimpseEditorDialog's mutations (#2427) are mocked here too, for the same
// reason.
vi.mock('@/magic/queries', () => ({
  useMotifStyleBindings: vi.fn(),
  useStyleCatalog: vi.fn(),
  useCharacterResonances: vi.fn(),
  useBindMotifStyle: vi.fn(),
  useUnbindMotifStyle: vi.fn(),
  useSetGlimpseTags: vi.fn(),
  useSetGlimpseProse: vi.fn(),
  useToggleGlimpseDistinction: vi.fn(),
  useTechniqueProgress: vi.fn(),
  useTrainTechnique: vi.fn(),
  useSetMotifFacet: () => ({ mutate: vi.fn(), isPending: false, isError: false, error: null }),
  // The technique picker (#4341): no manifesting technique, so it renders nothing.
  useManifestChoices: () => ({ data: [] }),
  useSetManifestChoice: () => ({ mutate: vi.fn(), isPending: false, isError: false, error: null }),
  // The aura card's reflections and the rite dialog it opens (#5124).
  useSettlingRite: vi.fn(),
  useReflectionOptions: vi.fn(),
  usePendingDriftConversionOffers: vi.fn(),
  usePerformSettlingRite: () => ({
    mutate: vi.fn(),
    reset: vi.fn(),
    isPending: false,
    isError: false,
    error: null,
  }),
}));

// Who the character is and whether they are unsettled come from the aura endpoint;
// the sheet payload carries the shares only.
vi.mock('@/magic/auraQueries', () => ({
  useCharacterAuras: vi.fn(),
}));

// GlimpseEditorDialog reads the catalog via the character-creation module's
// useGlimpseTags — mock it too so opening the dialog never issues a real fetch.
vi.mock('@/character-creation/queries', () => ({
  useGlimpseTags: vi.fn(),
  useFacets: () => ({ data: [] }),
  useAffinities: vi.fn(),
}));

import * as queries from '@/character_sheets/queries';
import * as magicQueries from '@/magic/queries';
import * as auraQueries from '@/magic/auraQueries';
import type { CharacterAura } from '@/magic/auraQueries';
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
  vi.mocked(magicQueries.useTechniqueProgress).mockReturnValue({
    data: [],
    isLoading: false,
  } as unknown as ReturnType<typeof magicQueries.useTechniqueProgress>);
  vi.mocked(magicQueries.useTrainTechnique).mockReturnValue({
    mutate: vi.fn(),
    isPending: false,
    isError: false,
    error: null,
  } as unknown as ReturnType<typeof magicQueries.useTrainTechnique>);
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
    stands_alone: false,
    offers: [],
  },
  {
    id: 2,
    axis: 'TONE',
    name: 'Dread',
    slug: 'dread',
    description: 'It felt wrong from the first instant.',
    example: 'The air went cold.',
    sort_order: 2,
    stands_alone: false,
    offers: [],
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
    shares: [
      { affinity_id: 2, affinity_name: 'Primal', percent: 70 },
      { affinity_id: 3, affinity_name: 'Abyssal', percent: 20 },
      { affinity_id: 1, affinity_name: 'Celestial', percent: 10 },
    ],
    dominant_affinity: 'Primal',
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
            catalog_name: 'Flare',
            level: 3,
            style: 'Manifestation',
            description: 'A burst of fire.',
            effect_summary: mockEffectSummary,
            forms: [mockBaseForm],
            signature: null,
            price: null,
            next_signature: null,
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
    resonances: [],
    ultimates: [],
    ...overrides,
  };
}

function makeOwnAura(overrides: Partial<CharacterAura> = {}): CharacterAura {
  return {
    id: 42,
    character: 1,
    shares: [
      { affinity_id: 2, affinity_name: 'Primal', percent: '58.00', settled_percent: '66.00' },
      { affinity_id: 3, affinity_name: 'Abyssal', percent: '42.00', settled_percent: '34.00' },
    ],
    dominant_affinity: 'Primal',
    dominant_affinity_display: 'Primal',
    unsettled: false,
    unsettled_line: '',
    unsettled_affinity_name: '',
    glimpse_state: 'COMPLETE',
    updated_at: '2026-11-14T00:00:00Z',
    ...overrides,
  };
}

function mockRiteReadings({
  reflections = [],
  deeds = [],
  offers = [],
}: {
  reflections?: unknown[];
  deeds?: unknown[];
  offers?: unknown[];
} = {}) {
  vi.mocked(magicQueries.useSettlingRite).mockReturnValue({
    data: {
      reflections,
      offerings: [],
      rite_ready: true,
      not_ready_message: '',
      check_name: 'Composure',
    },
  } as unknown as ReturnType<typeof magicQueries.useSettlingRite>);
  vi.mocked(magicQueries.useReflectionOptions).mockReturnValue({
    data: deeds,
  } as unknown as ReturnType<typeof magicQueries.useReflectionOptions>);
  vi.mocked(magicQueries.usePendingDriftConversionOffers).mockReturnValue({
    data: { results: offers },
  } as unknown as ReturnType<typeof magicQueries.usePendingDriftConversionOffers>);
}

function mockOwnAuras(auras: CharacterAura[]) {
  vi.mocked(auraQueries.useCharacterAuras).mockReturnValue({
    data: auras,
  } as unknown as ReturnType<typeof auraQueries.useCharacterAuras>);
}

describe('SpellbookTab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockOwnAuras([]);
    mockRiteReadings();
    mockMotifStyleQueries();
    mockGlimpseQueries();
    vi.mocked(cgQueries.useAffinities).mockReturnValue({
      data: [],
    } as unknown as ReturnType<typeof cgQueries.useAffinities>);
  });

  // #5206: the waiting sheet hands over its own payload; nothing is fetched by id.
  it('draws a payload it is handed and asks for no sheet', () => {
    mockPayload(undefined, { isLoading: true });
    renderWithProviders(
      <SpellbookTab
        characterId={7}
        isMyCharacter={false}
        payload={{ magic: makeMagic(), distinctions: [] }}
      />
    );
    expect(screen.getByText('Pyromancy')).toBeInTheDocument();
    expect(screen.queryByText('Reading their spellbook…')).not.toBeInTheDocument();
    expect(queries.useCharacterSheetQuery).toHaveBeenCalledWith(0);
    expect(queries.useCharacterSheetQuery).not.toHaveBeenCalledWith(7);
  });

  it('says it is reading while loading', () => {
    mockPayload(undefined, { isLoading: true });
    renderWithProviders(<SpellbookTab characterId={1} isMyCharacter={false} />);
    expect(screen.getByText('Reading their spellbook…')).toBeInTheDocument();
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

  it('draws the aura as a halo and says the split in words (#5123)', () => {
    // The halo carries the proportions and the sentence says them; the figures never
    // reach the page.
    mockPayload(
      makeMagic({
        aura: makeAura({
          shares: [
            { affinity_id: 3, affinity_name: 'Abyssal', percent: 50 },
            { affinity_id: 2, affinity_name: 'Primal', percent: 30 },
            { affinity_id: 1, affinity_name: 'Celestial', percent: 20 },
          ],
          dominant_affinity: 'Abyssal',
        }),
      })
    );
    renderWithProviders(<SpellbookTab characterId={1} isMyCharacter={false} />);

    const halo = screen.getByTestId('aura-halo');
    expect(halo).toHaveAttribute('data-affinities', 'abyssal primal celestial');
    expect(within(halo).getByTestId('aura-halo-sentence')).toHaveTextContent(
      'Half abyssal, a third primal, a fifth celestial.'
    );
    expect(screen.queryByText(/20|30|50/)).not.toBeInTheDocument();
    // A viewer who is not the owner sees no settled ring and no Settle button.
    expect(screen.queryByTestId('aura-halo-ring')).not.toBeInTheDocument();
    expect(screen.queryByTestId('settle-aura-button')).not.toBeInTheDocument();
  });

  it('explains each affinity the aura holds when the reader hovers over it', async () => {
    // Regression for #5293: staff write each affinity's description and no screen showed it.
    vi.mocked(cgQueries.useAffinities).mockReturnValue({
      data: [
        { id: 1, name: 'Celestial', description: 'What you give to others.' },
        { id: 2, name: 'Primal', description: 'What you feel.' },
        { id: 3, name: 'Abyssal', description: '' },
      ],
    } as unknown as ReturnType<typeof cgQueries.useAffinities>);
    mockPayload(
      makeMagic({
        aura: makeAura({
          shares: [
            { affinity_id: 2, affinity_name: 'Primal', percent: 70 },
            { affinity_id: 3, affinity_name: 'Abyssal', percent: 30 },
            { affinity_id: 1, affinity_name: 'Celestial', percent: 0 },
          ],
          dominant_affinity: 'Primal',
        }),
      })
    );
    renderWithProviders(<SpellbookTab characterId={1} isMyCharacter={false} />);

    const trigger = screen.getByTestId('aura-affinity-trigger');
    expect(within(trigger).getByTestId('aura-halo')).toBeInTheDocument();
    act(() => trigger.focus());
    const card = await screen.findByTestId('aura-affinity-explanation');
    // Primal is held and described; Abyssal is held with no words; Celestial is not held.
    expect(card).toHaveTextContent('What you feel.');
    expect(card).not.toHaveTextContent('Abyssal');
    expect(card).not.toHaveTextContent('What you give to others.');
  });

  it('draws the aura bare while no affinity it holds has a description (#5293)', () => {
    vi.mocked(cgQueries.useAffinities).mockReturnValue({
      data: [{ id: 2, name: 'Primal', description: '   ' }],
    } as unknown as ReturnType<typeof cgQueries.useAffinities>);
    mockPayload(makeMagic());
    renderWithProviders(<SpellbookTab characterId={1} isMyCharacter={false} />);
    expect(screen.queryByTestId('aura-affinity-trigger')).not.toBeInTheDocument();
  });

  it('draws the dashed settled ring for the owner (#5123)', () => {
    mockPayload(makeMagic());
    mockOwnAuras([makeOwnAura()]);
    renderWithProviders(<SpellbookTab characterId={1} isMyCharacter />);

    // One thin neutral dashed ring, not an arc per settled affinity in its own colour.
    const ring = screen.getByTestId('aura-halo-ring');
    expect(ring).toBeInTheDocument();
    expect(ring.childElementCount).toBe(0);
    expect(ring.querySelector('svg, circle')).toBeNull();
    expect(ring).not.toHaveAttribute('style');
    expect(screen.queryByTestId('aura-halo-status')).not.toBeInTheDocument();
    expect(screen.queryByTestId('settle-aura-button')).not.toBeInTheDocument();
  });

  it('shows Unsettled and the ruled line, with no Settle button while nothing is reflected', () => {
    const line = 'Your Domination has grown strong enough to make you unsettled.';
    mockPayload(makeMagic());
    mockOwnAuras([
      makeOwnAura({ unsettled: true, unsettled_line: line, unsettled_affinity_name: 'Abyssal' }),
    ]);
    renderWithProviders(<SpellbookTab characterId={1} isMyCharacter />);

    expect(screen.getByTestId('aura-halo-status')).toHaveTextContent('Unsettled');
    expect(screen.getByTestId('aura-halo-sentence')).toHaveTextContent(line);
    // The ring is tinted in the glow of the affinity that is unsettling them (as in the demo).
    expect(screen.getByTestId('aura-halo-ring').getAttribute('style')).toContain(
      '--aura-abyssal-glow'
    );
    // Nothing settles without a reflection behind it: no button, no card.
    expect(screen.queryByTestId('settle-aura-button')).not.toBeInTheDocument();
    expect(screen.queryByTestId('aura-reflections')).not.toBeInTheDocument();
  });

  it('lists waiting reflections, the unreflected deeds and the open chance, and opens the rite', async () => {
    const user = userEvent.setup();
    mockPayload(makeMagic());
    mockOwnAuras([makeOwnAura({ unsettled: true, unsettled_line: 'Unsettled line.' })]);
    mockRiteReadings({
      reflections: [
        {
          id: 1,
          choice: 'DISOWN',
          kind: 'resonance',
          title: 'Disown your Domination',
          where: '"The collar" · journal',
          from_line: 'from your journal, "The collar"',
          excerpt: 'I set the iron collar on the altar.',
          effect_line: 'Domination turns toward Fury, up to 3.',
        },
        {
          id: 2,
          choice: 'EMBRACE',
          kind: 'deed',
          title: "Embrace Barred the overseers' door",
          where: 'Pose in The Quarry',
          from_line: 'from your pose in The Quarry',
          excerpt: 'They had it coming.',
          effect_line: 'Your Domination from the door grows, up to 5.',
        },
      ],
      deeds: [
        { kind: 'deed', id: 9, label: 'Strike the chains loose · 3 Fury', replaces_waiting: false },
        { kind: 'burden', id: 61, label: 'The Mire you carry for Ysmay', replaces_waiting: false },
        { kind: 'burden', id: 62, label: 'The Mire you carry for Hobb', replaces_waiting: true },
        {
          kind: 'resonance',
          id: 4,
          label: 'Your Domination · unsettling you',
          replaces_waiting: true,
        },
      ],
      offers: [
        {
          id: 3,
          scene_id: null,
          character_id: 1,
          caps: [
            { target_resonance: { id: 7, name: 'Fury', affinity: 'Primal' }, cap_remaining: 3 },
          ],
        },
      ],
    });
    renderWithProviders(<SpellbookTab characterId={1} isMyCharacter />);

    const waiting = screen.getByTestId('aura-reflections-waiting');
    expect(waiting).toHaveTextContent('"The collar" · journal · Disown your Domination');
    expect(waiting).toHaveTextContent("Pose in The Quarry · Embrace Barred the overseers' door");
    // Deeds and burdens nobody has reflected on are "not yet reflected on"; the unsettling
    // resonance is a reflection target, and a burden with a reflection waiting is reflected on.
    const deeds = screen.getByTestId('aura-reflections-deeds');
    expect(deeds).toHaveTextContent('Strike the chains loose · 3 Fury');
    expect(deeds).toHaveTextContent('The Mire you carry for Ysmay');
    expect(deeds).not.toHaveTextContent('Hobb');
    expect(deeds).not.toHaveTextContent('unsettling you');
    expect(screen.getByTestId('aura-atone-chance')).toHaveTextContent(
      'A chance to atone is open: up to 3 toward Fury.'
    );

    await user.click(screen.getByTestId('settle-aura-button'));

    expect(await screen.findByText('Settling your aura')).toBeInTheDocument();
  });

  it('keeps the rite dialog open when the rite settles the last thing the card lists', async () => {
    const user = userEvent.setup();
    mockPayload(makeMagic());
    mockOwnAuras([makeOwnAura({ unsettled: true, unsettled_line: 'Unsettled line.' })]);
    mockRiteReadings({
      reflections: [
        {
          id: 1,
          choice: 'DISOWN',
          kind: 'resonance',
          title: 'Disown your Domination',
          where: '"The collar" · journal',
          from_line: 'from your journal, "The collar"',
          excerpt: 'I set the iron collar on the altar.',
          effect_line: 'Domination turns toward Fury, up to 3.',
        },
      ],
    });
    const queryClient = new QueryClient();
    const tree = () => (
      <Provider store={store}>
        <QueryClientProvider client={queryClient}>
          <MemoryRouter>
            <SpellbookTab characterId={1} isMyCharacter />
          </MemoryRouter>
        </QueryClientProvider>
      </Provider>
    );
    const { rerender } = render(tree());
    await user.click(screen.getByTestId('settle-aura-button'));
    expect(await screen.findByText('Settling your aura')).toBeInTheDocument();

    // The rite ran: nothing waits and nothing is left unreflected.
    mockRiteReadings();
    rerender(tree());

    expect(screen.getByText('Settling your aura')).toBeInTheDocument();
  });

  it('shows the card to the owner only', () => {
    mockPayload(makeMagic());
    mockRiteReadings({
      deeds: [{ kind: 'deed', id: 9, label: 'A deed', replaces_waiting: false }],
    });
    renderWithProviders(<SpellbookTab characterId={1} isMyCharacter={false} />);

    expect(screen.queryByTestId('aura-reflections')).not.toBeInTheDocument();
  });

  it('draws only the character own shares, with no Mire band (#5177)', () => {
    mockPayload(
      makeMagic({
        aura: makeAura({
          shares: [
            { affinity_id: 1, affinity_name: 'Celestial', percent: 56 },
            { affinity_id: 3, affinity_name: 'Abyssal', percent: 44 },
          ],
          dominant_affinity: 'Celestial',
        }),
      })
    );
    mockOwnAuras([makeOwnAura()]);
    renderWithProviders(<SpellbookTab characterId={1} isMyCharacter />);

    expect(screen.getByTestId('aura-halo')).toHaveAttribute('data-affinities', 'celestial abyssal');
    expect(screen.queryByTestId('aura-halo-mire-key')).not.toBeInTheDocument();
    expect(screen.queryByTestId('aura-halo-mire-line')).not.toBeInTheDocument();
    expect(screen.getByTestId('aura-halo-sentence')).toHaveTextContent(
      /^Half celestial, half abyssal\.$/
    );
  });

  it('sets the sentence in italics and the ring as one neutral dashed line (#5123)', () => {
    const css = readFileSync(
      path.resolve(
        path.dirname(fileURLToPath(import.meta.url)),
        '..',
        '..',
        'character_sheets',
        'sheet.css'
      ),
      'utf8'
    );
    const rule = (selector: string) =>
      css.match(new RegExp(`${selector.replace('.', '\\.')} \\{([^}]*)\\}`))?.[1] ?? '';
    expect(rule('.aura-halo-sentence')).toContain('font-style: italic');
    expect(rule('.aura-halo-ring')).toContain('1.5px dashed hsl(var(--muted-foreground))');
    // The old ring took each settled affinity's own colour from the aura tokens.
    expect(rule('.aura-halo-ring')).not.toContain('--aura-');
    // The Settle dialog portals out of .refsheet, so it carries the sheet's rust itself.
    expect(css).toMatch(
      /:root:not\(\[data-realm\]\) \.aura-settle-dialog \{\s*--primary: 10 60% 34%/
    );
  });

  it('has a sheet.css rule for every aura halo class it draws', () => {
    mockPayload(makeMagic());
    mockOwnAuras([makeOwnAura({ unsettled: true, unsettled_line: 'Unsettled line.' })]);
    const { container } = renderWithProviders(<SpellbookTab characterId={1} isMyCharacter />);
    const here = path.dirname(fileURLToPath(import.meta.url));
    const css = readFileSync(
      path.resolve(here, '..', '..', 'character_sheets', 'sheet.css'),
      'utf8'
    );
    const drawn = new Set<string>();
    container.querySelectorAll('[class]').forEach((node) => {
      node.classList.forEach((name) => {
        if (name.startsWith('aura-halo')) drawn.add(name);
      });
    });

    expect(drawn.size).toBeGreaterThan(4);
    for (const name of drawn) expect(css).toContain(`.${name}`);
  });

  it('draws the anima ritual, which the payload carried and nothing rendered (#3898)', () => {
    mockPayload(
      makeMagic({
        anima_ritual: {
          stat: 'Composure',
          skill: 'Ritual',
          primal_resonance: 'Silence',
          outward_resonance: 'Dread',
          description: 'She counts the coins in the dark until the counting is the only sound.',
        },
      })
    );
    renderWithProviders(<SpellbookTab characterId={1} isMyCharacter={false} />);

    expect(screen.getByTestId('spellbook-anima-ritual')).toBeInTheDocument();
    expect(
      screen.getByText('She counts the coins in the dark until the counting is the only sound.')
    ).toBeInTheDocument();
    expect(screen.getByText('Composure')).toBeInTheDocument();
    expect(screen.getByText('Silence')).toBeInTheDocument();
    expect(screen.getByText('Dread')).toBeInTheDocument();
  });

  it('draws no halo for an aura with nothing in it', () => {
    mockPayload(makeMagic({ aura: makeAura({ shares: [], dominant_affinity: '' }) }));
    renderWithProviders(<SpellbookTab characterId={1} isMyCharacter={false} />);
    expect(screen.queryByTestId('aura-halo')).not.toBeInTheDocument();
  });

  it('renders resonance balances (#3042)', () => {
    mockPayload(
      makeMagic({
        resonances: [
          { name: 'Ember', balance: 4, lifetime_earned: 12 },
          { name: 'Resolve', balance: 0, lifetime_earned: 3 },
        ],
      })
    );
    renderWithProviders(<SpellbookTab characterId={1} isMyCharacter={false} />);

    const card = screen.getByTestId('spellbook-resonances');
    const balances = within(card).getAllByTestId('resonance-balance');
    expect(balances).toHaveLength(2);
    expect(within(card).getByText('Ember')).toBeInTheDocument();
    // One sentence per resonance rather than a number tile beside a caption (#3898).
    expect(within(card).getByText('4 of 12 ever earned')).toBeInTheDocument();
  });

  it('omits the resonances card when there are no claimed resonances', () => {
    mockPayload(makeMagic({ resonances: [] }));
    renderWithProviders(<SpellbookTab characterId={1} isMyCharacter={false} />);
    expect(screen.queryByTestId('spellbook-resonances')).not.toBeInTheDocument();
  });

  it('renders known ultimates by name with their authored category label (#4098)', () => {
    mockPayload(
      makeMagic({
        ultimates: [{ name: 'Ember Ward', description: 'A ward', label: 'Wall' }],
      })
    );
    renderWithProviders(<SpellbookTab characterId={1} isMyCharacter={false} />);

    const card = screen.getByTestId('spellbook-ultimates');
    expect(within(card).getByText('Ember Ward')).toBeInTheDocument();
    expect(within(card).getByText('Wall')).toBeInTheDocument();
  });

  it('omits the ultimates section when none are known', () => {
    mockPayload(makeMagic({ ultimates: [] }));
    renderWithProviders(<SpellbookTab characterId={1} isMyCharacter={false} />);
    expect(screen.queryByTestId('spellbook-ultimates')).not.toBeInTheDocument();
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

  it('draws no workbench nav of its own, even for the owner (#3898)', () => {
    // The four links this used to end with belonged to a standalone tab. Inside the
    // Reference Sheet they sat under the section row and read as a second navigation
    // bar, so the sheet's own row is the only way out of Magic now.
    mockPayload(makeMagic());
    renderWithProviders(<SpellbookTab characterId={1} isMyCharacter={true} />);

    expect(screen.queryByRole('link', { name: /progression/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /sanctums/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /rituals/i })).not.toBeInTheDocument();
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

  it('keeps an editable Glimpse slot in staff edit mode, even when empty (#4224)', () => {
    mockPayload(makeMagic({ aura: makeAura({ glimpse_story: '' }) }));
    const stored = { prose: { glimpse: '' } } as unknown as CharacterSheetStaffEdit;
    renderWithProviders(
      <StaffEditContext.Provider value={{ sheetId: 1, stored }}>
        <SpellbookTab characterId={1} isMyCharacter={false} />
      </StaffEditContext.Provider>
    );
    expect(screen.getByRole('button', { name: 'Edit Glimpse' })).toBeInTheDocument();
  });

  it('draws no empty Glimpse slot outside edit mode', () => {
    mockPayload(makeMagic({ aura: makeAura({ glimpse_story: '' }) }));
    renderWithProviders(<SpellbookTab characterId={1} isMyCharacter={false} />);
    expect(screen.queryByRole('button', { name: 'Edit Glimpse' })).not.toBeInTheDocument();
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
      screen.getByText(/chosen the shape of it; write the story when ready/i)
    ).toBeInTheDocument();
  });

  it('omits the TAGS_ONLY prompt when the glimpse has not been started', () => {
    mockPayload(
      makeMagic({ aura: makeAura({ can_finish_glimpse: true, glimpse_state: 'NOT_STARTED' }) })
    );
    renderWithProviders(<SpellbookTab characterId={1} isMyCharacter={true} />);

    expect(screen.getByTestId('finish-glimpse-button')).toBeInTheDocument();
    expect(
      screen.queryByText(/chosen the shape of it; write the story when ready/i)
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
              feature: '',
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

      // is_from_glimpse was false for this CharacterDistinction (id 7): toggling
      // it calls the link (not unlink) side.
      expect(toggleDistinction).toHaveBeenCalledWith(7, false);
    });
  });
});

describe('SpellbookTab technique forms (#2901)', () => {
  const variantForm: TechniqueForm = {
    variant_id: 7,
    name: 'Ashfall Flare',
    resonance_id: 2,
    resonance_name: 'Cinder',
    intensity: 8,
    control: 3,
    is_default: true,
    is_locked: false,
    unlock_thread_level: 30,
    thread_level: 30,
    is_early: false,
    effect_summary: mockEffectSummary,
  };

  const lockedForm: TechniqueForm = {
    ...variantForm,
    variant_id: 9,
    name: 'Cinderfall Rite',
    is_default: false,
    is_locked: true,
    unlock_thread_level: 60,
  };

  beforeEach(() => {
    vi.clearAllMocks();
    mockMotifStyleQueries();
    mockGlimpseQueries();
  });

  function renderWithForms(forms: TechniqueForm[], signature: TechniqueSignature | null = null) {
    const magic = makeMagic();
    magic.gifts[0].techniques[0].forms = forms;
    magic.gifts[0].techniques[0].signature = signature;
    mockPayload(magic);
    renderWithProviders(<SpellbookTab characterId={1} isMyCharacter={false} />);
  }

  it('says nothing when the base form is all there is', () => {
    renderWithForms([{ ...mockBaseForm, is_default: true }]);
    expect(screen.queryByTestId('technique-forms')).not.toBeInTheDocument();
  });

  it('lists the base form alongside an unlocked variant, marking the default', () => {
    renderWithForms([{ ...mockBaseForm, is_default: false }, variantForm]);

    expect(screen.getByTestId('technique-forms')).toBeInTheDocument();
    expect(screen.getByText('base form')).toBeInTheDocument();
    expect(screen.getByText('Ashfall Flare (Cinder)')).toBeInTheDocument();
    expect(screen.getByText('default')).toBeInTheDocument();
    expect(screen.getByText(/intensity 8, control 3/)).toBeInTheDocument();
  });

  it('shows the next form as a goal rather than hiding it', () => {
    renderWithForms([mockBaseForm, lockedForm]);

    expect(screen.getByText('Not yet yours')).toBeInTheDocument();
    expect(screen.getByText('Cinderfall Rite (Cinder), at thread level 60')).toBeInTheDocument();
  });

  it('renders the signature as a delta, not another form row', () => {
    renderWithForms([mockBaseForm], {
      name: 'Sparks Answer Her Name',
      narrative_snippet: 'the sparks answer her name',
      intensity_delta: 1,
    });

    expect(screen.getByTestId('technique-signature')).toBeInTheDocument();
    expect(screen.getByText(/\+1 intensity/)).toBeInTheDocument();
    expect(screen.queryAllByTestId('technique-form')).toHaveLength(0);
  });
});

describe('SpellbookTab personalization (#4099)', () => {
  function baseForm(overrides: Partial<TechniqueForm> = {}): TechniqueForm {
    return { ...mockBaseForm, ...overrides };
  }

  function variantForm(overrides: Partial<TechniqueForm> = {}): TechniqueForm {
    return {
      variant_id: 7,
      name: 'Ashfall Flare',
      resonance_id: 2,
      resonance_name: 'Cinder',
      intensity: 8,
      control: 3,
      is_default: true,
      is_locked: false,
      unlock_thread_level: 30,
      thread_level: 30,
      is_early: false,
      effect_summary: mockEffectSummary,
      ...overrides,
    };
  }

  function mockTechnique(
    overrides: Partial<CharacterSheetTechnique> = {}
  ): CharacterSheetTechnique {
    const name = overrides.name ?? 'Flare';
    return {
      name,
      catalog_name: name,
      level: 3,
      style: 'Manifestation',
      description: 'A burst of fire.',
      effect_summary: mockEffectSummary,
      forms: [baseForm()],
      signature: null,
      price: null,
      next_signature: null,
      ...overrides,
    };
  }

  function renderSheetWith({ techniques }: { techniques: CharacterSheetTechnique[] }) {
    const magic = makeMagic();
    magic.gifts[0].techniques = techniques;
    mockPayload(magic);
    renderWithProviders(<SpellbookTab characterId={1} isMyCharacter={false} />);
  }

  beforeEach(() => {
    vi.clearAllMocks();
    mockMotifStyleQueries();
    mockGlimpseQueries();
  });

  it("titles the technique with the player's name and keeps the catalog name beside it", () => {
    renderSheetWith({
      techniques: [
        mockTechnique({
          name: 'Winterbite',
          catalog_name: 'Scorch Lash',
          description: 'Flame gutters to white.',
          price: {
            name: 'Frost on the skin',
            description: '',
            power_bonus: 4,
            consumes: [{ name: 'Shard of rime', quantity: 2 }],
            inflicts: 'Frostbitten fingers',
          },
          next_signature: { name: 'Rime walks with you', min_level: 30, thread_level: 10 },
        }),
      ],
    });
    const entry = screen.getByTestId('spellbook-technique');
    expect(within(entry).getByText('Winterbite')).toBeInTheDocument();
    expect(within(entry).getByText(/Scorch Lash · Level/)).toBeInTheDocument();
    expect(within(entry).getByText('Flame gutters to white.')).toBeInTheDocument();
    expect(within(entry).getByTestId('technique-price')).toHaveTextContent('Frost on the skin');
    expect(within(entry).getByTestId('technique-price-cost')).toHaveTextContent(
      'Consumes 2× Shard of rime · Inflicts Frostbitten fingers'
    );
    expect(within(entry).getByTestId('technique-next-signature')).toHaveTextContent(
      'Rime walks with you, at thread level 30'
    );
  });

  it('shows a bare "Level N" aside for an unpersonalized technique (#4099 parked minor)', () => {
    renderSheetWith({
      techniques: [mockTechnique({ name: 'Scorch Lash', catalog_name: 'Scorch Lash', level: 5 })],
    });
    const entry = screen.getByTestId('spellbook-technique');
    const aside = within(entry).getByText('Level 5');
    expect(aside).toHaveTextContent('Level 5');
    expect(aside.textContent).not.toContain('·');
    // Only one occurrence of the technique's name in the entry — no repeated
    // catalog-name clause alongside it.
    expect(within(entry).getAllByText('Scorch Lash')).toHaveLength(1);
  });

  it('marks a form bought early', () => {
    renderSheetWith({
      techniques: [
        mockTechnique({
          forms: [
            baseForm(),
            { ...variantForm(), is_early: true, name: 'Scorch Lash, frost-formed' },
          ],
        }),
      ],
    });
    expect(screen.getByText('early')).toBeInTheDocument();
  });

  it('keys technique rows by a stable id, not the display name (#4099 name collision)', () => {
    // A custom name can equal another selected technique's catalog name (the
    // server rejects this at creation time, but a pre-existing hold from
    // before that validation shipped could still collide) — React's list key
    // must stay unique even when two rows share the same displayed `name`.
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});
    renderSheetWith({
      techniques: [
        mockTechnique({ name: 'Winterbite', catalog_name: 'Scorch Lash' }),
        mockTechnique({ name: 'Winterbite', catalog_name: 'Winterbite' }),
      ],
    });
    const entries = screen.getAllByTestId('spellbook-technique');
    expect(entries).toHaveLength(2);
    const duplicateKeyWarning = consoleError.mock.calls.some((call) =>
      String(call[0]).includes('two children with the same key')
    );
    expect(duplicateKeyWarning).toBe(false);
    consoleError.mockRestore();
  });
});

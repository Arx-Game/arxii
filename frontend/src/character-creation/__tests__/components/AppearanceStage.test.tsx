/**
 * AppearanceStage Component Tests (folio, #3630; the controls as ruled in #5241)
 */

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { AppearanceStage } from '../../components/AppearanceStage';
import {
  createMockDraft,
  makeVisibleOffer,
  mockBuildAthletic,
  mockBuildAverage,
  mockCGExplanations,
  mockHeightBandAverage,
  mockHeightBandTall,
  mockHeightBandTowering,
  mockBeginnings,
  mockSpeciesHuman,
} from '../fixtures';
import { renderWithCharacterCreationProviders } from '../testUtils';
import type { OffersResponse } from '../../types';
import type { DraftDistinctionEntry } from '@/types/distinctions';
import { unreachableClasses } from './offers/classGuard';

const mutate = vi.fn();
let heightBands: (typeof mockHeightBandAverage)[] = [mockHeightBandAverage, mockHeightBandTall];
let copy: Record<string, string> = mockCGExplanations;

const black = { id: 5, name: 'black', display_name: 'Black', sort_order: 1, color_hex: '#1c1a1a' };
const prismatic = {
  id: 7,
  name: 'prismatic',
  display_name: 'Prismatic',
  sort_order: 2,
  color_hex: '',
};
const blue = { id: 6, name: 'blue', display_name: 'Blue', sort_order: 9, color_hex: '#3a6ea8' };
const pointed = { id: 11, name: 'pointed', display_name: 'Pointed', sort_order: 1, color_hex: '' };
const feline = { id: 12, name: 'feline', display_name: 'Feline', sort_order: 2, color_hex: '' };

vi.mock('../../queries', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../queries')>()),
  useCGExplanations: () => ({ data: copy }),
  useUpdateDraft: () => ({ mutate, mutateAsync: vi.fn() }),
  useHeightBands: () => ({ data: heightBands, isLoading: false }),
  useBuilds: () => ({ data: [mockBuildAverage, mockBuildAthletic], isLoading: false }),
  useFormOptions: () => ({
    data: {
      traits: [
        {
          trait: { id: 1, name: 'hair_color', display_name: 'Hair color', trait_type: 'color' },
          is_required: true,
          options: [black, prismatic],
          // Blue is not a colour this species lists: only a distinctive feature reaches it.
          all_options: [black, prismatic, blue],
        },
        {
          trait: { id: 2, name: 'ear_type', display_name: 'Ears', trait_type: 'feature' },
          is_required: false,
          options: [pointed, feline],
          all_options: [pointed, feline],
        },
      ],
      inherited: [],
    },
    isLoading: false,
  }),
  useDraftOffers: () => ({ data: offersResponse, isLoading: false }),
}));
vi.mock('../../api', () => ({
  listDraftMarkings: vi.fn().mockResolvedValue([]),
  createDraftMarking: vi.fn(),
  deleteDraftMarking: vi.fn(),
}));
vi.mock('@/hooks/useDistinctions', () => ({
  useDraftDistinctions: () => ({ data: draftDistinctions }),
  useSyncDistinctions: () => ({ mutate: syncMutate, pendingEntries: null }),
  usePendingSync: () => null,
}));

const syncMutate = vi.fn();
// The draft's distinction entries (#3739): a quality held on a trait is what opens
// that trait's widened palette and its description field.
let draftDistinctions: DraftDistinctionEntry[] = [];

const giantsBlood = makeVisibleOffer({
  offer_id: 201,
  distinction_id: 21,
  name: "Giant's Blood",
  distinction_name: "Giant's Blood",
  player_line: 'Unusual size and strength; the towering band opens.',
  opener_label: 'Frame',
  cost_per_rank: 20,
  opener_key: 'section:1',
});

const attractive = makeVisibleOffer({
  offer_id: 202,
  distinction_id: 22,
  name: 'Attractive',
  distinction_name: 'Attractive',
  player_line: 'Heads turn.',
  opener_label: 'Frame',
  max_rank: 3,
  opener_key: 'section:1',
});

/** A quality (#3739, #5241), offered on every feature. */
const alluring = makeVisibleOffer({
  offer_id: 901,
  distinction_id: 91,
  name: 'Alluring',
  distinction_name: 'Alluring',
  opener_label: 'a feature',
  opener_key: 'feature',
  max_rank: 5,
  cg_max_rank: 3,
  taken_per_feature: true,
});

function held(rank: number, trait: string): DraftDistinctionEntry {
  return {
    distinction_id: 91,
    distinction_name: 'Alluring',
    distinction_slug: 'alluring-feature',
    category_slug: 'physical',
    rank,
    cost: rank,
    notes: '',
    offer_ids: [901],
    sources: ['Hair color'],
    arrivals: ['choice'],
    feature_trait: trait,
    feature_marking: 0,
  };
}

let offersResponse: OffersResponse;

describe('AppearanceStage (folio)', () => {
  const draft = createMockDraft({
    selected_species: mockSpeciesHuman,
    height_band: mockHeightBandAverage,
    height_inches: 68,
  });
  const props = { draft, onRegisterBeforeLeave: vi.fn() } as const;

  beforeEach(() => {
    heightBands = [mockHeightBandAverage, mockHeightBandTall];
    copy = mockCGExplanations;
    offersResponse = { offers: [giantsBlood, attractive], terms: [], glimpse_cards: [] };
    draftDistinctions = [];
    syncMutate.mockClear();
    mutate.mockClear();
  });

  it('asks age and the birthday as numbers and height band and build as dropdowns', () => {
    renderWithCharacterCreationProviders(<AppearanceStage {...props} />);
    expect(screen.getByLabelText('Age')).toHaveAttribute('type', 'number');
    expect(screen.getByLabelText('Birthday month')).toHaveAttribute('type', 'number');
    expect(screen.getByLabelText('Birthday day')).toHaveAttribute('type', 'number');
    expect(screen.getByRole('combobox', { name: 'Height' })).toHaveValue(
      String(mockHeightBandAverage.id)
    );
    expect(screen.getByRole('combobox', { name: 'Build' })).toBeInTheDocument();
    // No row of a button per option is left on the stage (#5241).
    expect(screen.queryByRole('button', { name: mockHeightBandTall.display_name })).toBeNull();
    expect(screen.queryByRole('button', { name: draft.ic_month_names[0] })).toBeNull();
  });

  it('saves a birthday once both numbers are typed, held to the month’s last day', async () => {
    const user = userEvent.setup();
    renderWithCharacterCreationProviders(<AppearanceStage {...props} />);
    await user.type(screen.getByLabelText('Birthday month'), '2');
    await user.tab();
    // A month alone is not a birthday.
    expect(mutate).not.toHaveBeenCalledWith(
      expect.objectContaining({ data: expect.objectContaining({ birthday_month: 2 }) })
    );
    await user.type(screen.getByLabelText('Birthday day'), '31');
    await user.tab();
    expect(mutate).toHaveBeenCalledWith(
      expect.objectContaining({ data: { birthday_month: 2, birthday_day: 29 } })
    );
    expect(screen.getByLabelText('Birthday day')).toHaveValue(29);
  });

  it('reads a saved birthday back as the day of the game’s own month', () => {
    const born = createMockDraft({ ...draft, birthday_month: 3, birthday_day: 14 });
    renderWithCharacterCreationProviders(<AppearanceStage {...props} draft={born} />);
    const words = `Day 14 of ${born.ic_month_names[2]}`;
    // Beside the two numbers, and in the side panel's Birthday row.
    expect(screen.getAllByText(words)).toHaveLength(2);
    expect(screen.getByLabelText('Birthday month')).toHaveValue(3);
  });

  it('offers a colour as swatches in its own colour and writes the pick', async () => {
    const user = userEvent.setup();
    renderWithCharacterCreationProviders(<AppearanceStage {...props} />);
    const hair = screen.getByRole('group', { name: /Hair color/ });
    const swatch = within(hair).getByRole('button', { name: 'Black' });
    expect(swatch).toHaveAttribute('title', 'Black');
    expect(swatch.style.getPropertyValue('--swatch')).toBe('#1c1a1a');
    // No single colour: still a swatch, drawn striped.
    expect(within(hair).getByRole('button', { name: 'Prismatic' })).toHaveClass('no-hue');
    await user.click(swatch);
    expect(mutate).toHaveBeenCalledWith(
      expect.objectContaining({
        data: expect.objectContaining({
          draft_data: expect.objectContaining({
            form_traits: expect.objectContaining({ hair_color: 5 }),
          }),
        }),
      })
    );
  });

  it('prints the chosen colour’s name beside the feature’s name', () => {
    const chosen = createMockDraft({ ...draft, draft_data: { form_traits: { hair_color: 5 } } });
    renderWithCharacterCreationProviders(<AppearanceStage {...props} draft={chosen} />);
    const heading = screen.getByRole('heading', { name: /Hair color/ });
    expect(within(heading).getByText('Black')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Black' })).toHaveAttribute('aria-pressed', 'true');
  });

  it('offers a feature that is not a colour as one dropdown and writes the pick', async () => {
    const user = userEvent.setup();
    renderWithCharacterCreationProviders(<AppearanceStage {...props} />);
    const ears = screen.getByRole('combobox', { name: 'Ears' });
    await user.selectOptions(ears, 'Feline');
    expect(mutate).toHaveBeenCalledWith(
      expect.objectContaining({
        data: expect.objectContaining({
          draft_data: expect.objectContaining({
            form_traits: expect.objectContaining({ ear_type: 12 }),
          }),
        }),
      })
    );
  });

  it('states the age range from the draft payload and the world fact behind it (#3663)', () => {
    const misbegotten = createMockDraft({
      ...draft,
      age_min: 18,
      age_max: 20,
      selected_beginnings: {
        ...mockBeginnings,
        heritage: { name: 'Misbegotten', first_appeared_ic_year: 980 },
      },
    });
    renderWithCharacterCreationProviders(<AppearanceStage {...props} draft={misbegotten} />);
    expect(screen.getByText(/must be between 18 and 20 years\./)).toBeInTheDocument();
    expect(screen.getByText(/The first Misbegotten were born in 980 AS\./)).toBeInTheDocument();
  });

  it('says nothing about a heritage that has no anchor', () => {
    renderWithCharacterCreationProviders(<AppearanceStage {...props} />);
    expect(screen.getByText(/must be between 18 and 65 years\./)).toBeInTheDocument();
    expect(screen.queryByText(/were born in/)).toBeNull();
  });

  it('clamps a typed age to the payload ceiling', async () => {
    const user = userEvent.setup();
    const misbegotten = createMockDraft({ ...draft, age: 19, age_min: 18, age_max: 20 });
    renderWithCharacterCreationProviders(<AppearanceStage {...props} draft={misbegotten} />);
    const age = screen.getByLabelText('Age');
    await user.clear(age);
    await user.type(age, '30');
    await user.tab();
    expect(mutate).toHaveBeenCalledWith(
      expect.objectContaining({ data: expect.objectContaining({ age: 20 }) })
    );
  });

  it("offers this chapter's distinctions between the height line and the features (#3675 Task 15)", () => {
    renderWithCharacterCreationProviders(<AppearanceStage {...props} />);
    const heading = screen.getByRole('heading', { name: /What people notice first/ });
    expect(heading).toBeInTheDocument();
    expect(within(heading).getByText('offered here')).toBeInTheDocument();
    // Grouped by section (#3709): the section heading carries the Distinctions chip.
    expect(screen.getByText('Frame')).toBeInTheDocument();
    expect(screen.getByText('Distinctions')).toBeInTheDocument();
    expect(screen.getByText("Giant's Blood")).toBeInTheDocument();
    expect(screen.getByText('Attractive')).toBeInTheDocument();
    const follows = (earlier: Element, later: Element) =>
      Boolean(earlier.compareDocumentPosition(later) & Node.DOCUMENT_POSITION_FOLLOWING);
    const features = screen.getByRole('heading', { name: /Physical features/ });
    expect(follows(screen.getByLabelText('Inches'), heading)).toBe(true);
    expect(follows(heading, features)).toBe(true);
  });

  it("reads the chosen band's own authored cg_hint under the height (#3675 fix round 1)", () => {
    heightBands = [mockHeightBandAverage, mockHeightBandTall, mockHeightBandTowering];
    const towering = createMockDraft({ ...draft, height_band: mockHeightBandTowering });
    renderWithCharacterCreationProviders(<AppearanceStage {...props} draft={towering} />);
    expect(screen.getByText(mockHeightBandTowering.cg_hint)).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'Towering' })).toHaveAttribute(
      'title',
      mockHeightBandTowering.cg_hint
    );
  });

  it('marks a band players are not normally offered, for staff only', () => {
    heightBands = [mockHeightBandAverage, mockHeightBandTowering];
    const { unmount } = renderWithCharacterCreationProviders(<AppearanceStage {...props} />);
    expect(screen.getByRole('option', { name: 'Towering' })).toBeInTheDocument();
    unmount();
    renderWithCharacterCreationProviders(<AppearanceStage {...props} isStaff />);
    expect(
      screen.getByRole('option', { name: 'Towering (not normally offered)' })
    ).toBeInTheDocument();
  });

  it('shows the qualities on every feature with no step before them (#5241)', () => {
    offersResponse = { offers: [giantsBlood, attractive, alluring], terms: [], glimpse_cards: [] };
    renderWithCharacterCreationProviders(<AppearanceStage {...props} />);
    expect(screen.getByRole('group', { name: 'Alluring on Hair color' })).toBeInTheDocument();
    expect(screen.getByRole('group', { name: 'Alluring on Ears' })).toBeInTheDocument();
    expect(screen.queryByText(/make it distinctive/i)).toBeNull();
    const heading = screen.getByRole('heading', { name: /Physical features/ });
    expect(within(heading).getByText('0 of 10 feature points spent')).toBeInTheDocument();
  });

  it('says nothing of feature points when staff have authored no quality', () => {
    renderWithCharacterCreationProviders(<AppearanceStage {...props} />);
    expect(screen.queryByText(/feature points/i)).toBeNull();
    expect(screen.queryByRole('list', { name: /Qualities of/ })).toBeNull();
  });

  it('keeps the description shut and the palette narrow on a feature with no tier', () => {
    offersResponse = { offers: [giantsBlood, attractive, alluring], terms: [], glimpse_cards: [] };
    renderWithCharacterCreationProviders(<AppearanceStage {...props} />);
    expect(screen.queryByLabelText('Describe it')).toBeNull();
    expect(screen.queryByRole('button', { name: 'Blue' })).toBeNull();
  });

  it('opens the description and the whole palette on a feature that holds a tier', () => {
    offersResponse = { offers: [giantsBlood, attractive, alluring], terms: [], glimpse_cards: [] };
    draftDistinctions = [held(1, 'hair_color')];
    renderWithCharacterCreationProviders(<AppearanceStage {...props} />);
    // Only the feature that holds the tier opens.
    expect(screen.getAllByLabelText('Describe it')).toHaveLength(1);
    expect(screen.getByLabelText('Describe it')).toHaveAttribute('maxlength', '120');
    const unnatural = screen.getByRole('button', { name: 'Blue' });
    // Drawn apart from the species' own values.
    expect(unnatural).toHaveClass('beyond');
    expect(screen.getByRole('button', { name: 'Black' })).not.toHaveClass('beyond');
  });

  it('counts the first ten points as free and says what comes from CG points', () => {
    offersResponse = { offers: [alluring], terms: [], glimpse_cards: [] };
    const spent = createMockDraft({ ...draft, feature_points_spent: 12, feature_points_free: 10 });
    renderWithCharacterCreationProviders(<AppearanceStage {...props} draft={spent} />);
    const heading = screen.getByRole('heading', { name: /Physical features/ });
    expect(within(heading).getByText('10 of 10 feature points spent')).toBeInTheDocument();
    expect(screen.getByText('10 of 10 spent, 2 from CG points')).toBeInTheDocument();
  });

  it('lets go of a colour only a distinctive feature may hold when its last tier comes off', async () => {
    const user = userEvent.setup();
    offersResponse = { offers: [alluring], terms: [], glimpse_cards: [] };
    draftDistinctions = [held(1, 'hair_color')];
    const blueHaired = createMockDraft({
      ...draft,
      draft_data: { form_traits: { hair_color: blue.id, ear_type: pointed.id } },
    });
    renderWithCharacterCreationProviders(<AppearanceStage {...props} draft={blueHaired} />);
    await user.click(screen.getByRole('button', { name: 'Alluring on Hair color, tier 1' }));
    expect(syncMutate).toHaveBeenCalledWith([]);
    expect(mutate).toHaveBeenCalledWith(
      expect.objectContaining({
        data: { draft_data: expect.objectContaining({ form_traits: { ear_type: pointed.id } }) },
      })
    );
  });

  it('keeps a colour the species lists when the last tier comes off', async () => {
    const user = userEvent.setup();
    offersResponse = { offers: [alluring], terms: [], glimpse_cards: [] };
    draftDistinctions = [held(1, 'hair_color')];
    const blackHaired = createMockDraft({
      ...draft,
      draft_data: { form_traits: { hair_color: black.id } },
    });
    renderWithCharacterCreationProviders(<AppearanceStage {...props} draft={blackHaired} />);
    await user.click(screen.getByRole('button', { name: 'Alluring on Hair color, tier 1' }));
    expect(syncMutate).toHaveBeenCalledWith([]);
    expect(mutate).not.toHaveBeenCalledWith(
      expect.objectContaining({ data: expect.objectContaining({ draft_data: expect.anything() }) })
    );
  });

  it('does not mount a quality as a section of its own (#3739)', () => {
    offersResponse = { offers: [alluring], terms: [], glimpse_cards: [] };
    renderWithCharacterCreationProviders(<AppearanceStage {...props} />);
    // "a feature" is the generic opener label; it must never head a section.
    expect(screen.queryByRole('heading', { name: /a feature/i })).toBeNull();
    expect(screen.queryByRole('heading', { name: /What people notice first/ })).toBeNull();
  });

  it('asks a marking’s name, kind and region on one line, the last two as dropdowns', () => {
    const { container } = renderWithCharacterCreationProviders(<AppearanceStage {...props} />);
    const row = container.querySelector('.marking-row') as HTMLElement;
    expect(within(row).getByLabelText('Name')).toHaveAttribute('type', 'text');
    expect(within(row).getByRole('combobox', { name: 'Kind' })).toHaveValue('tattoo');
    expect(within(row).getByRole('combobox', { name: 'Region' })).toHaveValue('torso');
    expect(screen.queryByRole('button', { name: 'Left Arm' })).toBeNull();
  });

  it('emits no class hook that cg.css has no rule for (#3667 shape)', () => {
    heightBands = [mockHeightBandAverage, mockHeightBandTall, mockHeightBandTowering];
    offersResponse = { offers: [giantsBlood, attractive, alluring], terms: [], glimpse_cards: [] };
    draftDistinctions = [held(2, 'hair_color')];
    const { container } = renderWithCharacterCreationProviders(
      <div className="interview">
        <AppearanceStage {...props} />
      </div>
    );
    // Pre-existing folio-chassis classes with no rule reaching the bare
    // element (only a descendant selector, e.g. `.interview .leaf-body p`) -
    // ChapterLeaf/Marginalia primitives this stage mounts unchanged, not
    // created by this task's offers markup, same escape hatch every other
    // class-guard test uses.
    const styledElsewhere = new Set(['leaf-body', 'note-group']);
    expect(unreachableClasses(container, styledElsewhere)).toEqual([]);
  });
});

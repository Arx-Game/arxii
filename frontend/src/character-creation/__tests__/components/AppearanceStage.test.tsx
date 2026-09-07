/**
 * AppearanceStage Component Tests (folio, #3630)
 */

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { AppearanceStage } from '../../components/AppearanceStage';
import {
  createMockDraft,
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
import type { OffersResponse, VisibleOffer } from '../../types';
import { unreachableClasses } from './offers/classGuard';

const mutate = vi.fn();
let heightBands: (typeof mockHeightBandAverage)[] = [mockHeightBandAverage, mockHeightBandTall];
let copy: Record<string, string> = mockCGExplanations;

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
          options: [{ id: 5, name: 'black', display_name: 'Black', sort_order: 1 }],
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
  useDraftDistinctions: () => ({ data: [] }),
  useSyncDistinctions: () => ({ mutate: vi.fn() }),
}));

const giantsBlood: VisibleOffer = {
  offer_id: 201,
  distinction_id: 21,
  name: "Giant's Blood",
  player_line: 'Unusual size and strength; the towering band opens.',
  chapter: 'appearance',
  arrives_as: 'choice',
  opener_label: '',
  cost_per_rank: 20,
  max_rank: 1,
  is_locked: false,
  lock_reason: '',
};

const attractive: VisibleOffer = {
  offer_id: 202,
  distinction_id: 22,
  name: 'Attractive',
  player_line: 'Heads turn.',
  chapter: 'appearance',
  arrives_as: 'choice',
  opener_label: '',
  cost_per_rank: 1,
  max_rank: 3,
  is_locked: false,
  lock_reason: '',
};

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
    offersResponse = { offers: [giantsBlood, attractive], closed: [] };
  });

  it('offers height band and build as pressed rows and age as a field', () => {
    renderWithCharacterCreationProviders(<AppearanceStage {...props} />);
    expect(screen.getByRole('group', { name: 'Height band' })).toBeInTheDocument();
    expect(screen.getByRole('group', { name: 'Build' })).toBeInTheDocument();
    expect(screen.getByLabelText('Age')).toHaveAttribute('type', 'number');
  });

  it('writes a form trait choice into draft_data.form_traits', async () => {
    const user = userEvent.setup();
    renderWithCharacterCreationProviders(<AppearanceStage {...props} />);
    await user.click(screen.getByRole('button', { name: 'Black' }));
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

  it("offers this chapter's distinctions after the height block, with the heading fallback (#3675 Task 15)", () => {
    const { container } = renderWithCharacterCreationProviders(<AppearanceStage {...props} />);
    const heading = screen.getByText('What people notice first');
    expect(heading).toBeInTheDocument();
    expect(screen.getByText("Giant's Blood")).toBeInTheDocument();
    expect(screen.getByText('Attractive')).toBeInTheDocument();
    // After the height block (the height-in-inches field), before Build.
    const order = container.textContent ?? '';
    const heightIdx = order.indexOf('Height in inches');
    const offersIdx = order.indexOf('What people notice first');
    const buildIdx = order.indexOf('Build');
    expect(heightIdx).toBeGreaterThan(-1);
    expect(offersIdx).toBeGreaterThan(heightIdx);
    expect(buildIdx).toBeGreaterThan(offersIdx);
  });

  it('prints the closed hint with the closedLead fallback', () => {
    offersResponse = {
      offers: [giantsBlood],
      closed: [
        {
          distinction_id: 30,
          name: 'Impoverished',
          reason: 'Your route closed it.',
          opener_labels: [],
          opener_ids: [],
        },
      ],
    };
    renderWithCharacterCreationProviders(<AppearanceStage {...props} />);
    expect(
      screen.getByText('Closed by your route: Impoverished: Your route closed it.')
    ).toBeInTheDocument();
  });

  it('falls back to the inches range when a band carries no cg_hint (#3675 fix round 1)', () => {
    heightBands = [
      mockHeightBandAverage,
      mockHeightBandTall,
      { ...mockHeightBandTowering, cg_hint: '' },
    ];
    renderWithCharacterCreationProviders(<AppearanceStage {...props} />);
    const group = screen.getByRole('group', { name: 'Height band' });
    const towering = within(group).getByRole('button', { name: 'Towering' });
    expect(towering).toHaveAttribute('title', '79 to 96 inches');
  });

  it("reads a band's title from its own authored cg_hint column, not a name match (#3675 fix round 1)", () => {
    heightBands = [mockHeightBandAverage, mockHeightBandTall, mockHeightBandTowering];
    renderWithCharacterCreationProviders(<AppearanceStage {...props} />);
    const group = screen.getByRole('group', { name: 'Height band' });
    const towering = within(group).getByRole('button', { name: 'Towering' });
    expect(towering).toHaveAttribute('title', mockHeightBandTowering.cg_hint);
  });

  it('emits no class hook that cg.css has no rule for (#3667 shape)', () => {
    heightBands = [mockHeightBandAverage, mockHeightBandTall, mockHeightBandTowering];
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

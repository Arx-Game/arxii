/**
 * LineageStage Component Tests
 *
 * The Lineage step is built around Upbringings (#3617): pick an Upbringing for
 * the chosen Beginning, then its family path (claim a staff-authored family,
 * name a new one, or none), with typed prompts underneath.
 */

import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { LineageStage } from '../../components/LineageStage';
import * as api from '../../api';
import {
  mockDraftWithFamily,
  mockDraftWithHeritageNoUpbringing,
  mockDraftWithUpbringing,
  mockEmptyDraft,
  mockFamilyTemplate,
  mockNobleFamily,
  mockNobleFamily2,
  mockStartingArea,
  mockUpbringingClaim,
  mockUpbringingMultiPath,
  mockUpbringingNamed,
  mockUpbringingNamedWithTemplate,
  mockUpbringingUnknown,
  mockVacancyKin,
  mockCGExplanations,
  createMockDraft,
} from '../fixtures';
import {
  renderWithCharacterCreationProviders,
  createTestQueryClient,
  seedCharacterCreationQueries,
  seedQueryData,
} from '../testUtils';
import { characterCreationKeys } from '../../queries';
import { Stage } from '../../types';

// Mock the API module
vi.mock('../../api', () => ({
  getFamilies: vi.fn(),
  getOriginTemplates: vi.fn(),
  getClaimableTitles: vi.fn().mockResolvedValue([]),
  getHouseClaim: vi.fn().mockResolvedValue(null),
  submitHouseClaim: vi.fn(),
  updateDraft: vi.fn(),
  getTarotCards: vi.fn(),
  getNamingRitualConfig: vi.fn(),
  getCGExplanations: vi.fn(),
  getFamilySlots: vi.fn(),
  // Invented-parents card (#2815)
  getGenders: vi.fn().mockResolvedValue([]),
  getSpecies: vi.fn().mockResolvedValue([]),
  // FamilyPathSection queries vacancies from Task 9 on (#3648).
  getVacancies: vi.fn().mockResolvedValue([]),
}));

describe('LineageStage', () => {
  const mockOnStageSelect = vi.fn();

  beforeEach(() => {
    mockOnStageSelect.mockClear();
    vi.mocked(api.getFamilies).mockResolvedValue([]);
    vi.mocked(api.getOriginTemplates).mockResolvedValue([]);
    vi.mocked(api.getTarotCards).mockResolvedValue([]);
    vi.mocked(api.getNamingRitualConfig).mockResolvedValue({
      flavor_text: '',
      codex_entry_id: null,
    });
    vi.mocked(api.getFamilySlots).mockResolvedValue({ slots: [], pools: [] });
    vi.mocked(api.getCGExplanations).mockResolvedValue({});
  });

  describe('No Area Selected', () => {
    it('prompts user to select area first', () => {
      const queryClient = createTestQueryClient();

      renderWithCharacterCreationProviders(
        <LineageStage draft={mockEmptyDraft} onStageSelect={mockOnStageSelect} />,
        { queryClient }
      );

      expect(screen.getByText(/please select a starting area first/i)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /go to origin selection/i })).toBeInTheDocument();
    });

    it('navigates back to Origin stage when button clicked', async () => {
      const user = userEvent.setup();
      const queryClient = createTestQueryClient();

      renderWithCharacterCreationProviders(
        <LineageStage draft={mockEmptyDraft} onStageSelect={mockOnStageSelect} />,
        { queryClient }
      );

      const button = screen.getByRole('button', { name: /go to origin selection/i });
      await user.click(button);

      expect(mockOnStageSelect).toHaveBeenCalledWith(Stage.ORIGIN);
    });
  });

  describe('No Beginnings Selected', () => {
    it('prompts user to select a beginnings option first', () => {
      const queryClient = createTestQueryClient();
      const draft = createMockDraft({ ...mockEmptyDraft, selected_area: mockStartingArea });

      renderWithCharacterCreationProviders(
        <LineageStage draft={draft} onStageSelect={mockOnStageSelect} />,
        { queryClient }
      );

      expect(screen.getByText(/please select a beginnings option first/i)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /go to heritage selection/i })).toBeInTheDocument();
    });

    it('navigates back to Heritage stage when button clicked', async () => {
      const user = userEvent.setup();
      const queryClient = createTestQueryClient();
      const draft = createMockDraft({ ...mockEmptyDraft, selected_area: mockStartingArea });

      renderWithCharacterCreationProviders(
        <LineageStage draft={draft} onStageSelect={mockOnStageSelect} />,
        { queryClient }
      );

      const button = screen.getByRole('button', { name: /go to heritage selection/i });
      await user.click(button);

      expect(mockOnStageSelect).toHaveBeenCalledWith(Stage.HERITAGE);
    });
  });

  describe('Upbringing picker', () => {
    it('shows one card per upbringing with its cost and selects on click', async () => {
      vi.mocked(api.getOriginTemplates).mockResolvedValue([
        mockUpbringingNamed,
        mockUpbringingClaim,
      ]);
      const queryClient = createTestQueryClient();
      renderWithCharacterCreationProviders(
        <LineageStage draft={mockDraftWithHeritageNoUpbringing} onStageSelect={vi.fn()} />,
        { queryClient }
      );
      expect(await screen.findByText('Caretaker family')).toBeInTheDocument();
      expect(screen.getByText(/6 points/)).toBeInTheDocument();
      expect(screen.getByText('Ward of the House')).toBeInTheDocument();
      expect(screen.getByText(/free/i)).toBeInTheDocument();

      await userEvent.click(screen.getByText('Caretaker family'));
      expect(api.updateDraft).toHaveBeenCalledWith(
        mockDraftWithHeritageNoUpbringing.id,
        expect.objectContaining({ selected_origin_template_id: mockUpbringingNamed.id })
      );
    });

    it('shows a message when no upbringings are authored for the beginning', async () => {
      vi.mocked(api.getOriginTemplates).mockResolvedValue([]);
      const queryClient = createTestQueryClient();
      renderWithCharacterCreationProviders(
        <LineageStage draft={mockDraftWithHeritageNoUpbringing} onStageSelect={vi.fn()} />,
        { queryClient }
      );

      expect(
        await screen.findByText(/no upbringings are authored for this beginning yet/i)
      ).toBeInTheDocument();
    });

    it('shows a loading placeholder while upbringings load', () => {
      const queryClient = createTestQueryClient();
      renderWithCharacterCreationProviders(
        <LineageStage draft={mockDraftWithHeritageNoUpbringing} onStageSelect={vi.fn()} />,
        { queryClient }
      );

      expect(document.querySelector('.animate-pulse')).toBeInTheDocument();
    });
  });

  describe('Family path section', () => {
    it('auto-applies a single-path upbringing and shows the family-name input on the named path', async () => {
      const draft = createMockDraft({
        ...mockDraftWithHeritageNoUpbringing,
        selected_origin_template: mockUpbringingNamed,
      });
      const queryClient = createTestQueryClient();
      renderWithCharacterCreationProviders(<LineageStage draft={draft} onStageSelect={vi.fn()} />, {
        queryClient,
      });

      expect(await screen.findByLabelText(/family name/i)).toBeInTheDocument();
      expect(screen.queryByRole('radio')).not.toBeInTheDocument();
    });

    it('claim path shows family cards filtered by kind and the kin-slot picker', async () => {
      vi.mocked(api.getFamilies).mockResolvedValue([mockNobleFamily, mockNobleFamily2]);
      vi.mocked(api.getFamilySlots).mockResolvedValue({
        slots: [
          {
            id: 1,
            name: 'Heir',
            name_locked: false,
            description: 'The eldest child.',
            age_min: null,
            age_max: null,
            allowed_genders: [],
            family: mockNobleFamily.id,
          },
        ],
        pools: [],
      });
      const draft = createMockDraft({
        ...mockDraftWithUpbringing,
        family: mockNobleFamily,
      });
      const queryClient = createTestQueryClient();
      renderWithCharacterCreationProviders(<LineageStage draft={draft} onStageSelect={vi.fn()} />, {
        queryClient,
      });

      await waitFor(() => {
        expect(api.getFamilies).toHaveBeenCalledWith(mockStartingArea.id, [2]);
      });
      expect(await screen.findByText('Valardin')).toBeInTheDocument();
      expect(screen.getByText('Velenosa')).toBeInTheDocument();
      expect(await screen.findByText('Open Positions in This House')).toBeInTheDocument();
    });

    it('claim path shows a kin vacancy card instead of the kin-slot picker when kin vacancies are offered', async () => {
      vi.mocked(api.getVacancies).mockResolvedValue([mockVacancyKin]);
      const queryClient = createTestQueryClient();
      renderWithCharacterCreationProviders(
        <LineageStage draft={mockDraftWithFamily} onStageSelect={vi.fn()} />,
        { queryClient }
      );

      expect(await screen.findByText(mockVacancyKin.name)).toBeInTheDocument();
      expect(screen.queryByText('Open Positions in This House')).not.toBeInTheDocument();

      await userEvent.click(screen.getByRole('button', { name: new RegExp(mockVacancyKin.name) }));

      expect(api.updateDraft).toHaveBeenCalledWith(mockDraftWithFamily.id, {
        selected_vacancy_id: mockVacancyKin.id,
      });
    });

    it('none path shows the tarot naming ritual', async () => {
      const draft = createMockDraft({
        ...mockDraftWithHeritageNoUpbringing,
        selected_origin_template: mockUpbringingUnknown,
      });
      const queryClient = createTestQueryClient();
      // Pre-seed the tarot queries so the ritual mounts already-loaded: its
      // loading placeholder carries the same "Naming Ritual" heading as the
      // loaded state, so an async mock resolution races the assertion here.
      seedQueryData(queryClient, characterCreationKeys.tarotCards(), []);
      seedQueryData(queryClient, characterCreationKeys.namingRitualConfig(), {
        flavor_text: '',
        codex_entry_id: null,
      });
      renderWithCharacterCreationProviders(<LineageStage draft={draft} onStageSelect={vi.fn()} />, {
        queryClient,
      });

      expect(screen.getByText('Naming Ritual')).toBeInTheDocument();
    });

    it('shows a path picker for a multi-path upbringing and PATCHes family_path on pick', async () => {
      const draft = createMockDraft({
        ...mockDraftWithHeritageNoUpbringing,
        selected_origin_template: mockUpbringingMultiPath,
        family_path: 'claimed',
      });
      const queryClient = createTestQueryClient();
      renderWithCharacterCreationProviders(<LineageStage draft={draft} onStageSelect={vi.fn()} />, {
        queryClient,
      });

      const namedRadio = await screen.findByRole('radio', { name: /name a new family/i });
      await userEvent.click(namedRadio);

      expect(api.updateDraft).toHaveBeenCalledWith(draft.id, { family_path: 'named' });
    });
  });

  describe('Prompts', () => {
    it('a write-in prompt PATCHes draft_data.origin_slots', async () => {
      const draft = createMockDraft({
        ...mockDraftWithHeritageNoUpbringing,
        selected_origin_template: mockUpbringingNamed,
      });
      const queryClient = createTestQueryClient();
      renderWithCharacterCreationProviders(<LineageStage draft={draft} onStageSelect={vi.fn()} />, {
        queryClient,
      });

      const textarea = await screen.findByLabelText(
        /what trade did your adoptive family practice/i
      );
      await userEvent.type(textarea, 'W');

      await waitFor(() => {
        expect(api.updateDraft).toHaveBeenCalledWith(draft.id, {
          draft_data: { origin_slots: { '201': 'W' } },
        });
      });
    });

    it('pick-list buttons PATCH draft_data.origin_choices and price by the family influence', async () => {
      const influentialFamily = { ...mockNobleFamily, influence: 3 };
      vi.mocked(api.getFamilies).mockResolvedValue([influentialFamily]);
      const draft = createMockDraft({
        ...mockDraftWithUpbringing,
        family: influentialFamily,
      });
      const queryClient = createTestQueryClient();
      renderWithCharacterCreationProviders(<LineageStage draft={draft} onStageSelect={vi.fn()} />, {
        queryClient,
      });

      // Flat-cost choice: unaffected by influence.
      expect(await screen.findByText('2 pts')).toBeInTheDocument();
      // Per-influence choice: cost_per_influence (1) x influence (3).
      expect(screen.getByText('3 pts')).toBeInTheDocument();

      await userEvent.click(screen.getByText("A seat at the house's table"));

      expect(api.updateDraft).toHaveBeenCalledWith(draft.id, {
        draft_data: { origin_choices: { '202': 302 } },
      });
    });

    it('clicking an already-picked pick-list choice PATCHes origin_choices with null', async () => {
      const draft = createMockDraft({
        ...mockDraftWithUpbringing,
        family: mockNobleFamily,
        draft_data: { origin_choices: { '202': 302 } },
      });
      const queryClient = createTestQueryClient();
      renderWithCharacterCreationProviders(<LineageStage draft={draft} onStageSelect={vi.fn()} />, {
        queryClient,
      });

      await userEvent.click(await screen.findByText("A seat at the house's table"));

      expect(api.updateDraft).toHaveBeenCalledWith(draft.id, {
        draft_data: { origin_choices: { '202': null } },
      });
    });

    it('hides a prompt scoped to the claimed path when on the named path', async () => {
      const draft = createMockDraft({
        ...mockDraftWithHeritageNoUpbringing,
        selected_origin_template: mockUpbringingMultiPath,
        family_path: 'named',
      });
      const queryClient = createTestQueryClient();
      renderWithCharacterCreationProviders(<LineageStage draft={draft} onStageSelect={vi.fn()} />, {
        queryClient,
      });

      expect(await screen.findByText('Describe your childhood home.')).toBeInTheDocument();
      expect(screen.queryByText('What does the house expect of you?')).not.toBeInTheDocument();
    });

    it('renders a path-scoped prompt after the Your Family heading', async () => {
      const draft = createMockDraft({
        ...mockDraftWithHeritageNoUpbringing,
        selected_origin_template: mockUpbringingMultiPath,
        family_path: 'claimed',
      });
      const queryClient = createTestQueryClient();
      renderWithCharacterCreationProviders(<LineageStage draft={draft} onStageSelect={vi.fn()} />, {
        queryClient,
      });

      const heading = await screen.findByText('Your Family');
      const prompt = await screen.findByText('What does the house expect of you?');
      expect(
        heading.compareDocumentPosition(prompt) & Node.DOCUMENT_POSITION_FOLLOWING
      ).toBeTruthy();
    });
  });

  describe('Family Template (name path)', () => {
    it('clicking a Family Template aspect option PATCHes family_aspect_picks', async () => {
      const draft = createMockDraft({
        ...mockDraftWithHeritageNoUpbringing,
        selected_origin_template: mockUpbringingNamedWithTemplate,
      });
      const queryClient = createTestQueryClient();
      renderWithCharacterCreationProviders(<LineageStage draft={draft} onStageSelect={vi.fn()} />, {
        queryClient,
      });

      const charge = mockFamilyTemplate.aspect_definitions[0];
      expect(await screen.findByText(charge.prompt)).toBeInTheDocument();
      await userEvent.click(screen.getByRole('button', { name: /Granaries/ }));

      expect(api.updateDraft).toHaveBeenCalledWith(draft.id, {
        draft_data: { family_aspect_picks: { [charge.id]: [charge.options[0].id] } },
      });
    });

    it('offers a Family Template choice row when the Upbringing offers more than one, and PATCHes on pick', async () => {
      const secondTemplate = { ...mockFamilyTemplate, id: 402, name: 'Alternate Trust' };
      const draft = createMockDraft({
        ...mockDraftWithHeritageNoUpbringing,
        selected_origin_template: {
          ...mockUpbringingNamedWithTemplate,
          family_templates: [mockFamilyTemplate, secondTemplate],
        },
      });
      const queryClient = createTestQueryClient();
      renderWithCharacterCreationProviders(<LineageStage draft={draft} onStageSelect={vi.fn()} />, {
        queryClient,
      });

      const option = await screen.findByRole('button', { name: mockFamilyTemplate.name });
      expect(screen.getByRole('button', { name: secondTemplate.name })).toBeInTheDocument();
      await userEvent.click(option);

      expect(api.updateDraft).toHaveBeenCalledWith(draft.id, {
        draft_data: { family_template_id: mockFamilyTemplate.id },
      });
    });

    it('choosing an already-chosen Family Template again PATCHes family_template_id with null', async () => {
      const secondTemplate = { ...mockFamilyTemplate, id: 402, name: 'Alternate Trust' };
      const draft = createMockDraft({
        ...mockDraftWithHeritageNoUpbringing,
        selected_origin_template: {
          ...mockUpbringingNamedWithTemplate,
          family_templates: [mockFamilyTemplate, secondTemplate],
        },
        draft_data: { family_template_id: mockFamilyTemplate.id },
      });
      const queryClient = createTestQueryClient();
      renderWithCharacterCreationProviders(<LineageStage draft={draft} onStageSelect={vi.fn()} />, {
        queryClient,
      });

      const option = await screen.findByRole('button', { name: mockFamilyTemplate.name });
      await userEvent.click(option);

      expect(api.updateDraft).toHaveBeenCalledWith(draft.id, {
        draft_data: { family_template_id: null },
      });
    });

    it('choosing a served house option PATCHes served_house_id', async () => {
      const draft = createMockDraft({
        ...mockDraftWithHeritageNoUpbringing,
        selected_origin_template: mockUpbringingNamedWithTemplate,
      });
      const queryClient = createTestQueryClient();
      renderWithCharacterCreationProviders(<LineageStage draft={draft} onStageSelect={vi.fn()} />, {
        queryClient,
      });

      const houseChoice = mockFamilyTemplate.served_house_choices[0];
      await userEvent.click(await screen.findByRole('button', { name: houseChoice.name }));

      expect(api.updateDraft).toHaveBeenCalledWith(draft.id, {
        served_house_id: houseChoice.id,
      });
    });
  });

  describe('Page Header', () => {
    it('titles the chapter leaf with the authored Upbringing copy', async () => {
      const queryClient = createTestQueryClient();
      seedCharacterCreationQueries(queryClient, { explanations: mockCGExplanations });

      renderWithCharacterCreationProviders(
        <LineageStage
          draft={mockDraftWithHeritageNoUpbringing}
          onStageSelect={mockOnStageSelect}
        />,
        { queryClient }
      );

      expect(screen.getByRole('heading', { name: 'Your Upbringing' })).toBeInTheDocument();
      expect(
        screen.getByText('Choose how you were raised, then settle your family.')
      ).toBeInTheDocument();
    });
  });
});

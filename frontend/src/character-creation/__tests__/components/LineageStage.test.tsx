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
  mockDraftWithHeritageNoUpbringing,
  mockDraftWithUpbringing,
  mockEmptyDraft,
  mockNobleFamily,
  mockNobleFamily2,
  mockStartingArea,
  mockUpbringingClaim,
  mockUpbringingMultiPath,
  mockUpbringingNamed,
  mockUpbringingUnknown,
  createMockDraft,
} from '../fixtures';
import {
  renderWithCharacterCreationProviders,
  createTestQueryClient,
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
  });

  describe('Page Header', () => {
    it('displays stage title and description', async () => {
      const queryClient = createTestQueryClient();

      renderWithCharacterCreationProviders(
        <LineageStage
          draft={mockDraftWithHeritageNoUpbringing}
          onStageSelect={mockOnStageSelect}
        />,
        { queryClient }
      );

      expect(screen.getByText('Your Upbringing')).toBeInTheDocument();
    });
  });
});

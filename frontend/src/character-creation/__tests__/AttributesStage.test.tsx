/**
 * AttributesStage Component Tests
 *
 * Tests for the attributes allocation stage, including:
 * - Stat rendering (12 stats in 4 categories)
 * - The purse at the head of the frame
 * - Disabled raise-button titles
 * - The margin gloss (pressing a statistic's name)
 * - Value changes (1-5 scale, no internal conversion)
 */

import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AttributesStage } from '../components/AttributesStage';
import type { CharacterDraft } from '../types';
import { mockEmptyDraft } from './fixtures';

// Create test query client
const createTestQueryClient = () =>
  new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

// Mock the query hooks AttributesStage and SkillsSection consume.
const mockUpdateDraftMutate = vi.fn();
vi.mock('../queries', () => ({
  useUpdateDraft: () => ({
    mutate: mockUpdateDraftMutate,
    isLoading: false,
  }),
  useStatDefinitions: () => ({
    data: [
      { id: 1, name: 'strength', description: 'Raw physical power and muscle.' },
      { id: 2, name: 'agility', description: 'Speed, reflexes, and coordination.' },
      { id: 3, name: 'stamina', description: 'Endurance and resistance to harm.' },
      { id: 4, name: 'charm', description: 'Likability and social magnetism.' },
      { id: 5, name: 'presence', description: 'Force of personality and leadership.' },
      { id: 6, name: 'composure', description: 'Grace under pressure and emotional control.' },
      { id: 7, name: 'intellect', description: 'Reasoning and learned knowledge.' },
      { id: 8, name: 'wits', description: 'Quick thinking and situational awareness.' },
      { id: 9, name: 'stability', description: 'Mental resilience and groundedness.' },
      { id: 10, name: 'luck', description: 'Fortune and serendipity.' },
      {
        id: 11,
        name: 'perception',
        description: 'Awareness and reading of people and situations.',
      },
      { id: 12, name: 'willpower', description: 'Mental fortitude and determination.' },
    ],
    isLoading: false,
  }),
  useCGExplanations: () => ({ data: undefined, isLoading: false }),
  // SkillsSection is imported by AttributesStage; mockEmptyDraft has no
  // selected_path so SkillsSection never actually mounts, but the module
  // still needs every hook it consumes to exist.
  useSkills: () => ({ data: undefined, isLoading: false, error: null }),
  useSkillPointBudget: () => ({ data: undefined, isLoading: false, error: null }),
  usePathSkillSuggestions: () => ({ data: undefined, isLoading: false, error: null }),
}));

/** Helper: default stats object with all 12 stats at value 2. */
const defaultStats = () => ({
  strength: 2,
  agility: 2,
  stamina: 2,
  charm: 2,
  presence: 2,
  composure: 2,
  intellect: 2,
  wits: 2,
  stability: 2,
  luck: 2,
  perception: 2,
  willpower: 2,
});

describe('AttributesStage', () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  const renderAttributesStage = (draft: CharacterDraft) => {
    const queryClient = createTestQueryClient();
    return render(
      <QueryClientProvider client={queryClient}>
        <AttributesStage draft={draft} />
      </QueryClientProvider>
    );
  };

  describe('Initial Render', () => {
    it('renders all 12 primary stats', () => {
      const draft: CharacterDraft = {
        ...mockEmptyDraft,
        draft_data: { stats: defaultStats() },
      };

      renderAttributesStage(draft);

      expect(screen.getByRole('button', { name: /^strength$/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /^agility$/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /^stamina$/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /^charm$/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /^presence$/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /^composure$/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /^intellect$/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /^wits$/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /^stability$/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /^luck$/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /^perception$/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /^willpower$/i })).toBeInTheDocument();
    });

    it('renders category headers', () => {
      const draft: CharacterDraft = {
        ...mockEmptyDraft,
        draft_data: { stats: defaultStats() },
      };

      renderAttributesStage(draft);

      expect(screen.getByText('Physical')).toBeInTheDocument();
      expect(screen.getByText('Social')).toBeInTheDocument();
      expect(screen.getByText('Mental')).toBeInTheDocument();
      expect(screen.getByText('Meta')).toBeInTheDocument();
    });

    it('displays stats with default values (2) when no stats set', () => {
      const draft: CharacterDraft = {
        ...mockEmptyDraft,
        draft_data: {},
      };

      renderAttributesStage(draft);

      // All stats should display as 2
      const statValues = screen.getAllByText('2');
      expect(statValues.length).toBeGreaterThanOrEqual(12);
    });
  });

  describe('Display Values', () => {
    it('displays value 5 directly', () => {
      const draft: CharacterDraft = {
        ...mockEmptyDraft,
        stats_points_remaining: 2,
        stats_budget: 29,
        draft_data: {
          stats: {
            ...defaultStats(),
            strength: 5,
          },
        },
      };

      renderAttributesStage(draft);

      expect(screen.getByText('5')).toBeInTheDocument();
    });

    it('displays value 1 directly', () => {
      const draft: CharacterDraft = {
        ...mockEmptyDraft,
        stats_points_remaining: 6,
        stats_budget: 29,
        draft_data: {
          stats: {
            ...defaultStats(),
            strength: 1,
          },
        },
      };

      renderAttributesStage(draft);

      expect(screen.getByText('1')).toBeInTheDocument();
    });
  });

  describe('The purse and its instruments', () => {
    it('shows the purse at the head of the frame', () => {
      const draft: CharacterDraft = {
        ...mockEmptyDraft,
        draft_data: { stats: defaultStats() },
        stats_points_remaining: 16,
        stats_budget: 40,
      };
      renderAttributesStage(draft);
      expect(screen.getByText(/points remaining/i).closest('.instr-ledger')).toHaveClass('head');
      expect(screen.getByText('16')).toBeInTheDocument();
    });

    it('explains a disabled raise button in its title', () => {
      const draft: CharacterDraft = {
        ...mockEmptyDraft,
        draft_data: { stats: { ...defaultStats(), strength: 5 } },
        stats_points_remaining: 0,
        stats_budget: 40,
      };
      renderAttributesStage(draft);
      expect(screen.getByRole('button', { name: /raise strength/i })).toHaveAttribute(
        'title',
        'At 5, the most it can be'
      );
      expect(screen.getByRole('button', { name: /raise agility/i })).toHaveAttribute(
        'title',
        'No points remain; lower another to raise this one'
      );
    });

    it('writes the pressed statistic into the margin', async () => {
      const draft: CharacterDraft = {
        ...mockEmptyDraft,
        draft_data: { stats: defaultStats() },
      };
      renderAttributesStage(draft);
      await userEvent.click(screen.getByRole('button', { name: /^strength$/i }));
      const margin = within(screen.getByRole('complementary'));
      expect(margin.getByRole('status')).toHaveTextContent('Raw physical power and muscle.');
    });
  });

  describe('Stat Modification', () => {
    it('calls updateDraft with direct value when increasing a stat', async () => {
      const user = userEvent.setup();
      const draft: CharacterDraft = {
        ...mockEmptyDraft,
        draft_data: { stats: defaultStats() },
      };

      renderAttributesStage(draft);

      await user.click(screen.getByRole('button', { name: /raise charm/i }));

      expect(mockUpdateDraftMutate).toHaveBeenCalledWith(
        expect.objectContaining({
          draftId: draft.id,
          data: expect.objectContaining({
            draft_data: expect.objectContaining({
              stats: expect.objectContaining({
                charm: 3,
              }),
            }),
          }),
        })
      );
    });

    it('calls updateDraft with direct value when decreasing a stat', async () => {
      const user = userEvent.setup();
      const draft: CharacterDraft = {
        ...mockEmptyDraft,
        stats_points_remaining: 4,
        stats_budget: 29,
        draft_data: {
          stats: {
            ...defaultStats(),
            charm: 3,
          },
        },
      };

      renderAttributesStage(draft);

      await user.click(screen.getByRole('button', { name: /lower charm/i }));

      expect(mockUpdateDraftMutate).toHaveBeenCalledWith(
        expect.objectContaining({
          draftId: draft.id,
          data: expect.objectContaining({
            draft_data: expect.objectContaining({
              stats: expect.objectContaining({
                charm: 2,
              }),
            }),
          }),
        })
      );
    });
  });
});

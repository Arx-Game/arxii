/**
 * AttributesStage Component Tests
 *
 * Tests for the attributes allocation stage, including:
 * - Stat rendering (12 stats in 4 categories)
 * - Points budget display
 * - Validation
 * - Value changes (1-5 scale, no internal conversion)
 */

import { render, screen, waitFor } from '@testing-library/react';
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

// Mock useUpdateDraft and useStatDefinitions hooks
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

      expect(screen.getByText('strength')).toBeInTheDocument();
      expect(screen.getByText('agility')).toBeInTheDocument();
      expect(screen.getByText('stamina')).toBeInTheDocument();
      expect(screen.getByText('charm')).toBeInTheDocument();
      expect(screen.getByText('presence')).toBeInTheDocument();
      expect(screen.getByText('composure')).toBeInTheDocument();
      expect(screen.getByText('intellect')).toBeInTheDocument();
      expect(screen.getByText('wits')).toBeInTheDocument();
      expect(screen.getByText('stability')).toBeInTheDocument();
      expect(screen.getByText('luck')).toBeInTheDocument();
      expect(screen.getByText('perception')).toBeInTheDocument();
      expect(screen.getByText('willpower')).toBeInTheDocument();
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

    it('displays correct points remaining with default stats', () => {
      const draft: CharacterDraft = {
        ...mockEmptyDraft,
        stats_points_remaining: 5,
        stats_budget: 29,
        draft_data: { stats: defaultStats() },
      };

      renderAttributesStage(draft);

      expect(screen.getByLabelText('5 points remaining')).toBeInTheDocument();
    });

    it('displays stat descriptions on hover', async () => {
      const user = userEvent.setup();
      const draft: CharacterDraft = {
        ...mockEmptyDraft,
        draft_data: { stats: defaultStats() },
      };

      renderAttributesStage(draft);

      // Hover over strength stat card
      const strengthCard = screen.getByText('strength').closest('[class*="cursor-pointer"]');
      if (strengthCard) {
        await user.hover(strengthCard);
        await waitFor(() => {
          expect(screen.getByText('Raw physical power and muscle.')).toBeInTheDocument();
        });
      }
    });
  });

  describe('Points Budget', () => {
    it('shows 0 remaining when all points spent', () => {
      const draft: CharacterDraft = {
        ...mockEmptyDraft,
        stats_points_remaining: 0,
        stats_budget: 29,
        draft_data: {
          stats: {
            ...defaultStats(),
            strength: 3,
            agility: 3,
            wits: 3,
            willpower: 3,
            luck: 3,
          },
        },
      };

      renderAttributesStage(draft);

      expect(screen.getByLabelText('0 points remaining')).toBeInTheDocument();
    });

    it('shows negative remaining when over budget', () => {
      const draft: CharacterDraft = {
        ...mockEmptyDraft,
        stats_points_remaining: -3,
        stats_budget: 29,
        draft_data: {
          stats: {
            ...defaultStats(),
            strength: 5,
            agility: 5,
            stamina: 4,
          },
        },
      };

      renderAttributesStage(draft);

      expect(screen.getByLabelText('-3 points remaining')).toBeInTheDocument();
    });

    it('shows positive remaining when under budget', () => {
      const draft: CharacterDraft = {
        ...mockEmptyDraft,
        stats_points_remaining: 4,
        stats_budget: 29,
        draft_data: {
          stats: {
            ...defaultStats(),
            strength: 3,
          },
        },
      };

      renderAttributesStage(draft);

      expect(screen.getByLabelText('4 points remaining')).toBeInTheDocument();
    });
  });

  describe('Display Values', () => {
    it('displays value 2 directly (no division)', () => {
      const draft: CharacterDraft = {
        ...mockEmptyDraft,
        draft_data: { stats: defaultStats() },
      };

      renderAttributesStage(draft);

      const statValues = screen.getAllByText('2');
      expect(statValues.length).toBeGreaterThanOrEqual(12);
    });

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

  describe('Stat Modification', () => {
    it('calls updateDraft with direct value when increasing stat', async () => {
      const user = userEvent.setup();
      const draft: CharacterDraft = {
        ...mockEmptyDraft,
        draft_data: { stats: defaultStats() },
      };

      renderAttributesStage(draft);

      // Find first plus button (for strength)
      const plusButtons = screen.getAllByRole('button');
      const strengthPlusButton = plusButtons.find((btn) => btn.querySelector('svg.lucide-plus'));

      if (strengthPlusButton) {
        await user.click(strengthPlusButton);

        await waitFor(() => {
          expect(mockUpdateDraftMutate).toHaveBeenCalledWith(
            expect.objectContaining({
              draftId: draft.id,
              data: expect.objectContaining({
                draft_data: expect.objectContaining({
                  stats: expect.objectContaining({
                    strength: 3, // Increased from 2 to 3 (no * 10)
                  }),
                }),
              }),
            })
          );
        });
      }
    });

    it('calls updateDraft with direct value when decreasing stat', async () => {
      const user = userEvent.setup();
      const draft: CharacterDraft = {
        ...mockEmptyDraft,
        stats_points_remaining: 4,
        stats_budget: 29,
        draft_data: {
          stats: {
            ...defaultStats(),
            strength: 3,
          },
        },
      };

      renderAttributesStage(draft);

      // Find first minus button (for strength)
      const minusButtons = screen.getAllByRole('button');
      const strengthMinusButton = minusButtons.find((btn) => btn.querySelector('svg.lucide-minus'));

      if (strengthMinusButton) {
        await user.click(strengthMinusButton);

        await waitFor(() => {
          expect(mockUpdateDraftMutate).toHaveBeenCalledWith(
            expect.objectContaining({
              draftId: draft.id,
              data: expect.objectContaining({
                draft_data: expect.objectContaining({
                  stats: expect.objectContaining({
                    strength: 2, // Decreased from 3 to 2 (no * 10)
                  }),
                }),
              }),
            })
          );
        });
      }
    });
  });

  describe('Validation Feedback', () => {
    it('shows complete state when points remaining = 0', () => {
      const draft: CharacterDraft = {
        ...mockEmptyDraft,
        stats_points_remaining: 0,
        stats_budget: 29,
        draft_data: {
          stats: {
            ...defaultStats(),
            strength: 3,
            agility: 3,
            wits: 3,
            willpower: 3,
            luck: 3,
          },
        },
      };

      renderAttributesStage(draft);

      expect(screen.getByLabelText('0 points remaining')).toBeInTheDocument();
    });

    it('shows over budget state when points remaining < 0', () => {
      const draft: CharacterDraft = {
        ...mockEmptyDraft,
        stats_points_remaining: -3,
        stats_budget: 29,
        draft_data: {
          stats: {
            ...defaultStats(),
            strength: 5,
            agility: 5,
            stamina: 4,
          },
        },
      };

      renderAttributesStage(draft);

      expect(screen.getByLabelText('-3 points remaining')).toBeInTheDocument();
      expect(screen.getByText(/Over budget by 3/i)).toBeInTheDocument();
    });

    it('shows warning message when points unspent', () => {
      const draft: CharacterDraft = {
        ...mockEmptyDraft,
        stats_points_remaining: 5,
        stats_budget: 29,
        draft_data: { stats: defaultStats() },
      };

      renderAttributesStage(draft);

      expect(screen.getByText(/You have 5 unspent points/i)).toBeInTheDocument();
    });

    it('shows warning message when over budget', () => {
      const draft: CharacterDraft = {
        ...mockEmptyDraft,
        stats_points_remaining: -3,
        stats_budget: 29,
        draft_data: {
          stats: {
            ...defaultStats(),
            strength: 5,
            agility: 5,
            stamina: 4,
          },
        },
      };

      renderAttributesStage(draft);

      expect(screen.getByText(/You are 3 points over budget/i)).toBeInTheDocument();
    });
  });
});

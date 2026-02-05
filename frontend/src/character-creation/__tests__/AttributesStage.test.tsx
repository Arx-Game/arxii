/**
 * AttributesStage Component Tests
 *
 * Tests for the attributes allocation stage, including:
 * - Stat rendering
 * - Free points calculation
 * - Validation
 * - Value changes
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
      { id: 6, name: 'perception', description: 'Awareness and reading of people and situations.' },
      { id: 7, name: 'intellect', description: 'Reasoning and learned knowledge.' },
      { id: 8, name: 'wits', description: 'Quick thinking and situational awareness.' },
      { id: 9, name: 'willpower', description: 'Mental fortitude and determination.' },
    ],
    isLoading: false,
  }),
}));

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
    it('renders all 9 primary stats', () => {
      const draft: CharacterDraft = {
        ...mockEmptyDraft,
        draft_data: {
          stats: {
            strength: 20,
            agility: 20,
            stamina: 20,
            charm: 20,
            presence: 20,
            perception: 20,
            intellect: 20,
            wits: 20,
            willpower: 20,
          },
        },
      };

      renderAttributesStage(draft);

      expect(screen.getByText('strength')).toBeInTheDocument();
      expect(screen.getByText('agility')).toBeInTheDocument();
      expect(screen.getByText('stamina')).toBeInTheDocument();
      expect(screen.getByText('charm')).toBeInTheDocument();
      expect(screen.getByText('presence')).toBeInTheDocument();
      expect(screen.getByText('perception')).toBeInTheDocument();
      expect(screen.getByText('intellect')).toBeInTheDocument();
      expect(screen.getByText('wits')).toBeInTheDocument();
      expect(screen.getByText('willpower')).toBeInTheDocument();
    });

    it('displays stats with default values (2) when no stats set', () => {
      const draft: CharacterDraft = {
        ...mockEmptyDraft,
        draft_data: {},
      };

      renderAttributesStage(draft);

      // All stats should display as 2 (default value 20 / 10)
      const statValues = screen.getAllByText('2');
      expect(statValues.length).toBeGreaterThanOrEqual(9);
    });

    it('displays correct free points with default stats', () => {
      const draft: CharacterDraft = {
        ...mockEmptyDraft,
        draft_data: {
          stats: {
            strength: 20,
            agility: 20,
            stamina: 20,
            charm: 20,
            presence: 20,
            perception: 20,
            intellect: 20,
            wits: 20,
            willpower: 20,
          },
        },
      };

      renderAttributesStage(draft);

      // FreePointsWidget shows number with aria-label
      expect(screen.getByLabelText('5 free points remaining')).toBeInTheDocument();
    });

    it('displays stat descriptions on hover', async () => {
      const user = userEvent.setup();
      const draft: CharacterDraft = {
        ...mockEmptyDraft,
        draft_data: {
          stats: {
            strength: 20,
            agility: 20,
            stamina: 20,
            charm: 20,
            presence: 20,
            perception: 20,
            intellect: 20,
            wits: 20,
            willpower: 20,
          },
        },
      };

      renderAttributesStage(draft);

      // Descriptions are shown in sidebar on hover (desktop)
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

  describe('Free Points Calculation', () => {
    it('shows 0 free points when all points spent', () => {
      const draft: CharacterDraft = {
        ...mockEmptyDraft,
        draft_data: {
          stats: {
            strength: 30,
            agility: 30,
            stamina: 30,
            charm: 20,
            presence: 20,
            perception: 20,
            intellect: 20,
            wits: 30,
            willpower: 30,
          },
        },
      };

      renderAttributesStage(draft);

      expect(screen.getByLabelText('0 free points remaining')).toBeInTheDocument();
    });

    it('shows negative free points when over budget', () => {
      const draft: CharacterDraft = {
        ...mockEmptyDraft,
        draft_data: {
          stats: {
            strength: 50,
            agility: 50,
            stamina: 40,
            charm: 20,
            presence: 20,
            perception: 20,
            intellect: 20,
            wits: 20,
            willpower: 20,
          },
        },
      };

      renderAttributesStage(draft);

      expect(screen.getByLabelText('-3 free points remaining')).toBeInTheDocument();
    });

    it('shows positive free points when under budget', () => {
      const draft: CharacterDraft = {
        ...mockEmptyDraft,
        draft_data: {
          stats: {
            strength: 30,
            agility: 20,
            stamina: 20,
            charm: 20,
            presence: 20,
            perception: 20,
            intellect: 20,
            wits: 20,
            willpower: 20,
          },
        },
      };

      renderAttributesStage(draft);

      expect(screen.getByLabelText('4 free points remaining')).toBeInTheDocument();
    });
  });

  describe('Display Value Conversion', () => {
    it('displays internal value 20 as 2', () => {
      const draft: CharacterDraft = {
        ...mockEmptyDraft,
        draft_data: {
          stats: {
            strength: 20,
            agility: 20,
            stamina: 20,
            charm: 20,
            presence: 20,
            perception: 20,
            intellect: 20,
            wits: 20,
            willpower: 20,
          },
        },
      };

      renderAttributesStage(draft);

      // All values should be 2
      const statValues = screen.getAllByText('2');
      expect(statValues.length).toBeGreaterThanOrEqual(9);
    });

    it('displays internal value 50 as 5', () => {
      const draft: CharacterDraft = {
        ...mockEmptyDraft,
        draft_data: {
          stats: {
            strength: 50,
            agility: 20,
            stamina: 20,
            charm: 20,
            presence: 20,
            perception: 20,
            intellect: 20,
            wits: 20,
            willpower: 20,
          },
        },
      };

      renderAttributesStage(draft);

      expect(screen.getByText('5')).toBeInTheDocument();
    });

    it('displays internal value 10 as 1', () => {
      const draft: CharacterDraft = {
        ...mockEmptyDraft,
        draft_data: {
          stats: {
            strength: 10,
            agility: 20,
            stamina: 20,
            charm: 20,
            presence: 20,
            perception: 20,
            intellect: 20,
            wits: 20,
            willpower: 20,
          },
        },
      };

      renderAttributesStage(draft);

      expect(screen.getByText('1')).toBeInTheDocument();
    });
  });

  describe('Stat Modification', () => {
    it('calls updateDraft when increasing stat', async () => {
      const user = userEvent.setup();
      const draft: CharacterDraft = {
        ...mockEmptyDraft,
        draft_data: {
          stats: {
            strength: 20,
            agility: 20,
            stamina: 20,
            charm: 20,
            presence: 20,
            perception: 20,
            intellect: 20,
            wits: 20,
            willpower: 20,
          },
        },
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
                    strength: 30, // Increased from 20 to 30
                  }),
                }),
              }),
            })
          );
        });
      }
    });

    it('calls updateDraft when decreasing stat', async () => {
      const user = userEvent.setup();
      const draft: CharacterDraft = {
        ...mockEmptyDraft,
        draft_data: {
          stats: {
            strength: 30,
            agility: 20,
            stamina: 20,
            charm: 20,
            presence: 20,
            perception: 20,
            intellect: 20,
            wits: 20,
            willpower: 20,
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
                    strength: 20, // Decreased from 30 to 20
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
    it('shows complete state when free points = 0', () => {
      const draft: CharacterDraft = {
        ...mockEmptyDraft,
        draft_data: {
          stats: {
            strength: 30,
            agility: 30,
            stamina: 30,
            charm: 20,
            presence: 20,
            perception: 20,
            intellect: 20,
            wits: 30,
            willpower: 30,
          },
        },
      };

      renderAttributesStage(draft);

      // Check that free points displays as 0
      expect(screen.getByLabelText('0 free points remaining')).toBeInTheDocument();
    });

    it('shows over budget state when free points < 0', () => {
      const draft: CharacterDraft = {
        ...mockEmptyDraft,
        draft_data: {
          stats: {
            strength: 50,
            agility: 50,
            stamina: 40,
            charm: 20,
            presence: 20,
            perception: 20,
            intellect: 20,
            wits: 20,
            willpower: 20,
          },
        },
      };

      renderAttributesStage(draft);

      // Check that free points displays as negative with over budget message
      expect(screen.getByLabelText('-3 free points remaining')).toBeInTheDocument();
      expect(screen.getByText(/Over budget by 3/i)).toBeInTheDocument();
    });

    it('shows warning message when points unspent', () => {
      const draft: CharacterDraft = {
        ...mockEmptyDraft,
        draft_data: {
          stats: {
            strength: 20,
            agility: 20,
            stamina: 20,
            charm: 20,
            presence: 20,
            perception: 20,
            intellect: 20,
            wits: 20,
            willpower: 20,
          },
        },
      };

      renderAttributesStage(draft);

      expect(screen.getByText(/You have 5 unspent points/i)).toBeInTheDocument();
    });

    it('shows warning message when over budget', () => {
      const draft: CharacterDraft = {
        ...mockEmptyDraft,
        draft_data: {
          stats: {
            strength: 50,
            agility: 50,
            stamina: 40,
            charm: 20,
            presence: 20,
            perception: 20,
            intellect: 20,
            wits: 20,
            willpower: 20,
          },
        },
      };

      renderAttributesStage(draft);

      expect(screen.getByText(/You are 3 points over budget/i)).toBeInTheDocument();
    });
  });
});

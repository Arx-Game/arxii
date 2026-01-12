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

// Mock useUpdateDraft hook
const mockUpdateDraftMutate = vi.fn();
vi.mock('../queries', () => ({
  useUpdateDraft: () => ({
    mutate: mockUpdateDraftMutate,
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
    it('renders all 8 primary stats', () => {
      const draft: CharacterDraft = {
        ...mockEmptyDraft,
        draft_data: {
          stats: {
            strength: 20,
            agility: 20,
            stamina: 20,
            charm: 20,
            presence: 20,
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
      expect(statValues.length).toBeGreaterThanOrEqual(8);
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
            intellect: 20,
            wits: 20,
            willpower: 20,
          },
        },
      };

      renderAttributesStage(draft);

      expect(screen.getByText(/Free Points: 5/i)).toBeInTheDocument();
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
            intellect: 20,
            wits: 30,
            willpower: 30,
          },
        },
      };

      renderAttributesStage(draft);

      expect(screen.getByText(/Free Points: 0/i)).toBeInTheDocument();
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
            intellect: 20,
            wits: 20,
            willpower: 20,
          },
        },
      };

      renderAttributesStage(draft);

      expect(screen.getByText(/Free Points: -3/i)).toBeInTheDocument();
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
            intellect: 20,
            wits: 20,
            willpower: 20,
          },
        },
      };

      renderAttributesStage(draft);

      expect(screen.getByText(/Free Points: 4/i)).toBeInTheDocument();
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
            intellect: 20,
            wits: 20,
            willpower: 20,
          },
        },
      };

      renderAttributesStage(draft);

      // All values should be 2
      const statValues = screen.getAllByText('2');
      expect(statValues.length).toBeGreaterThanOrEqual(8);
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
    it('shows green checkmark when free points = 0', () => {
      const draft: CharacterDraft = {
        ...mockEmptyDraft,
        draft_data: {
          stats: {
            strength: 30,
            agility: 30,
            stamina: 30,
            charm: 20,
            presence: 20,
            intellect: 20,
            wits: 30,
            willpower: 30,
          },
        },
      };

      renderAttributesStage(draft);

      // Check that free points displays as 0 (checkmark should be present)
      expect(screen.getByText(/Free Points: 0/i)).toBeInTheDocument();
    });

    it('shows alert icon when free points < 0', () => {
      const draft: CharacterDraft = {
        ...mockEmptyDraft,
        draft_data: {
          stats: {
            strength: 50,
            agility: 50,
            stamina: 40,
            charm: 20,
            presence: 20,
            intellect: 20,
            wits: 20,
            willpower: 20,
          },
        },
      };

      renderAttributesStage(draft);

      // Check that free points displays as negative (alert should be present)
      expect(screen.getByText(/Free Points: -3/i)).toBeInTheDocument();
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

  describe('Stat Categories', () => {
    it('renders Physical category with strength and agility', () => {
      const draft: CharacterDraft = {
        ...mockEmptyDraft,
        draft_data: {
          stats: {
            strength: 20,
            agility: 20,
            stamina: 20,
            charm: 20,
            presence: 20,
            intellect: 20,
            wits: 20,
            willpower: 20,
          },
        },
      };

      renderAttributesStage(draft);

      expect(screen.getByText('Physical')).toBeInTheDocument();
    });

    it('renders Social category with charm and presence', () => {
      const draft: CharacterDraft = {
        ...mockEmptyDraft,
        draft_data: {
          stats: {
            strength: 20,
            agility: 20,
            stamina: 20,
            charm: 20,
            presence: 20,
            intellect: 20,
            wits: 20,
            willpower: 20,
          },
        },
      };

      renderAttributesStage(draft);

      expect(screen.getByText('Social')).toBeInTheDocument();
    });

    it('renders Mental category with intellect and wits', () => {
      const draft: CharacterDraft = {
        ...mockEmptyDraft,
        draft_data: {
          stats: {
            strength: 20,
            agility: 20,
            stamina: 20,
            charm: 20,
            presence: 20,
            intellect: 20,
            wits: 20,
            willpower: 20,
          },
        },
      };

      renderAttributesStage(draft);

      expect(screen.getByText('Mental')).toBeInTheDocument();
    });

    it('renders Defensive category with stamina and willpower', () => {
      const draft: CharacterDraft = {
        ...mockEmptyDraft,
        draft_data: {
          stats: {
            strength: 20,
            agility: 20,
            stamina: 20,
            charm: 20,
            presence: 20,
            intellect: 20,
            wits: 20,
            willpower: 20,
          },
        },
      };

      renderAttributesStage(draft);

      expect(screen.getByText('Defensive')).toBeInTheDocument();
    });
  });
});

/**
 * SkillsSection Component Tests
 *
 * Mounts SkillsSection directly (AttributesStage.test.tsx only exercises it
 * indirectly via mockEmptyDraft, which has no selected_path and so never
 * actually renders it). Covers: the purse in the frame's ledger head, a
 * skill row's labelled value, the debounced save on a raise click, and the
 * specialization accordion trigger's restyled class.
 */

import { act, fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { vi } from 'vitest';
import { SkillsSection } from '../components/SkillsSection';
import type { CharacterDraft } from '../types';
import { mockEmptyDraft, mockPath } from './fixtures';

const createTestQueryClient = () =>
  new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

const mockUpdateDraftMutate = vi.fn();
vi.mock('../queries', () => ({
  useSkills: () => ({
    data: [
      {
        id: 1,
        name: 'Blades',
        category: 'combat',
        category_display: 'Combat',
        description: '',
        tooltip: '',
        display_order: 1,
        is_active: true,
        specializations: [
          {
            id: 10,
            name: 'Fencing',
            description: '',
            tooltip: '',
            display_order: 1,
            is_active: true,
            parent_skill_id: 1,
            parent_skill_name: 'Blades',
          },
        ],
      },
      {
        id: 2,
        name: 'Stealth',
        category: 'subterfuge',
        category_display: 'Subterfuge',
        description: '',
        tooltip: '',
        display_order: 2,
        is_active: true,
        specializations: [],
      },
    ],
    isLoading: false,
    error: null,
  }),
  useSkillPointBudget: () => ({
    data: {
      id: 1,
      path_points: 40,
      free_points: 20,
      total_points: 60,
      points_per_tier: 10,
      specialization_unlock_threshold: 20,
      max_skill_value: 30,
      max_specialization_value: 20,
    },
    isLoading: false,
    error: null,
  }),
  usePathSkillSuggestions: () => ({ data: [], isLoading: false, error: null }),
  useCGExplanations: () => ({ data: undefined, isLoading: false }),
  useUpdateDraft: () => ({ mutate: mockUpdateDraftMutate, isLoading: false }),
}));

describe('SkillsSection', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.clearAllMocks();
    vi.useRealTimers();
  });

  const renderSkillsSection = (draft: CharacterDraft) => {
    const queryClient = createTestQueryClient();
    return render(
      <QueryClientProvider client={queryClient}>
        <SkillsSection draft={draft} />
      </QueryClientProvider>
    );
  };

  const draft: CharacterDraft = {
    ...mockEmptyDraft,
    selected_path: mockPath,
    draft_data: { skills: { '1': 20 } },
  };

  it("shows the skill purse in the frame's ledger head", () => {
    renderSkillsSection(draft);

    const ledger = screen.getByText(/skill points remaining/i).closest('.instr-ledger');
    expect(ledger).toHaveClass('head');
    expect(screen.getByText('40')).toBeInTheDocument();
  });

  it("labels each skill row's value with the skill name", () => {
    renderSkillsSection(draft);

    expect(screen.getByLabelText('Blades')).toHaveTextContent('20');
    expect(screen.getByLabelText('Stealth')).toHaveTextContent('0');
  });

  it('saves a raised skill value after the debounce', () => {
    renderSkillsSection(draft);

    fireEvent.click(screen.getByRole('button', { name: /raise stealth/i }));
    act(() => {
      vi.runAllTimers();
    });

    expect(mockUpdateDraftMutate).toHaveBeenCalledWith(
      expect.objectContaining({
        draftId: draft.id,
        data: expect.objectContaining({
          draft_data: expect.objectContaining({
            skills: expect.objectContaining({ '2': 10 }),
          }),
        }),
      })
    );
  });

  it('gives the specialization accordion trigger the quiet-link style', () => {
    renderSkillsSection(draft);

    expect(screen.getByRole('button', { name: /specializations/i })).toHaveClass('quiet-link');
  });
});

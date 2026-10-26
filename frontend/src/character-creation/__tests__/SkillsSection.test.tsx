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
let mockSuggestions: Array<{
  skill_id: number;
  skill_name: string;
  suggested_value: number;
}> = [];
let mockCopy: Record<string, string> | undefined;
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
      {
        id: 3,
        name: 'Occult',
        category: 'magic',
        category_display: 'Magic',
        description: '',
        tooltip: '',
        display_order: 3,
        is_active: true,
        specializations: [
          {
            id: 30,
            name: 'Wards',
            description: '',
            tooltip: '',
            display_order: 1,
            is_active: true,
            parent_skill_id: 3,
            parent_skill_name: 'Occult',
          },
        ],
      },
      {
        id: 4,
        name: 'Ritualism',
        category: 'magic',
        category_display: 'Magic',
        description: '',
        tooltip: '',
        display_order: 4,
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
  usePathSkillSuggestions: () => ({ data: mockSuggestions, isLoading: false, error: null }),
  useCGExplanations: () => ({ data: mockCopy, isLoading: false }),
  useUpdateDraft: () => ({ mutate: mockUpdateDraftMutate, isLoading: false }),
}));

describe('SkillsSection', () => {
  beforeEach(() => {
    mockSuggestions = [];
    mockCopy = undefined;
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

  it("states the ledger head's left text as a true fact about the budget", () => {
    renderSkillsSection(draft);

    expect(screen.getByText('Skills rise in steps of ten, to 30')).toBeInTheDocument();
  });

  it('gives the raise button a reason when the skill is at its cap', () => {
    const atCapDraft: CharacterDraft = {
      ...mockEmptyDraft,
      selected_path: mockPath,
      draft_data: { skills: { '1': 30 } },
    };
    renderSkillsSection(atCapDraft);

    expect(screen.getByRole('button', { name: /raise blades/i })).toHaveAttribute(
      'title',
      'At 30, the most it can be'
    );
  });

  it('gives the raise button a reason when the purse is empty', () => {
    const emptyPurseDraft: CharacterDraft = {
      ...mockEmptyDraft,
      selected_path: mockPath,
      draft_data: { skills: { '1': 25, '2': 30 } },
    };
    renderSkillsSection(emptyPurseDraft);

    expect(screen.getByRole('button', { name: /raise blades/i })).toHaveAttribute(
      'title',
      'No skill points remain; lower another to raise this one'
    );
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

  describe('Magic skills (#4457)', () => {
    const lastSavedSkills = () => {
      const call = mockUpdateDraftMutate.mock.calls.at(-1);
      return call?.[0].data.draft_data.skills as Record<string, number>;
    };

    it('offers no stepper for a Magic skill', () => {
      renderSkillsSection(draft);

      expect(screen.queryByRole('button', { name: /raise occult/i })).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: /lower occult/i })).not.toBeInTheDocument();
      expect(screen.getByRole('button', { name: /raise stealth/i })).toBeInTheDocument();
    });

    it('lists each Magic skill at its training allocation, read-only (#4659)', () => {
      renderSkillsSection({
        ...draft,
        magic_training: {
          ...mockEmptyDraft.magic_training,
          total: 40,
          required_spend: 40,
          allocated: 40,
          skills: [
            { id: 3, name: 'Occult', value: 30, max: 30 },
            { id: 4, name: 'Ritualism', value: 10, max: 30 },
          ],
        },
      });

      expect(screen.getByText('From your Tradition training')).toBeInTheDocument();
      expect(screen.getByLabelText('Occult')).toHaveTextContent('30');
      expect(screen.getByLabelText('Ritualism')).toHaveTextContent('10');
      expect(screen.queryByText(/your magic skills start untrained/i)).not.toBeInTheDocument();
    });

    it('says the Magic skills start untrained when nothing is allocated', () => {
      renderSkillsSection(draft);

      expect(
        screen.getByText(
          'Your Magic skills start untrained. They grow with use and weekly training, faster with a mentor, and an Academy course speeds that up.'
        )
      ).toBeInTheDocument();
      expect(screen.queryByLabelText('Occult')).not.toBeInTheDocument();
      expect(screen.queryByText('From your Tradition training')).not.toBeInTheDocument();
    });

    it('reads both lines from the explanation copy when staff wrote them', () => {
      mockCopy = {
        skills_magic_granted_heading: 'Schooling',
        skills_magic_granted_none: 'Nothing yet.',
      };
      const { unmount } = renderSkillsSection({
        ...draft,
        magic_training: {
          ...mockEmptyDraft.magic_training,
          total: 40,
          required_spend: 40,
          allocated: 40,
          skills: [
            { id: 3, name: 'Occult', value: 30, max: 30 },
            { id: 4, name: 'Ritualism', value: 10, max: 30 },
          ],
        },
      });
      expect(screen.getByText('Schooling')).toBeInTheDocument();
      unmount();

      renderSkillsSection(draft);
      expect(screen.getByText('Nothing yet.')).toBeInTheDocument();
    });

    it('does not apply a path suggestion that names a Magic skill', () => {
      mockSuggestions = [
        { skill_id: 1, skill_name: 'Blades', suggested_value: 20 },
        { skill_id: 3, skill_name: 'Occult', suggested_value: 20 },
      ];
      renderSkillsSection({ ...draft, draft_data: {} });

      expect(screen.getByLabelText('Blades')).toHaveTextContent('20');
      expect(screen.getByText(/suggested skills: Blades 20\./)).toBeInTheDocument();
      expect(screen.queryByText(/Occult 20/)).not.toBeInTheDocument();

      fireEvent.click(screen.getByRole('button', { name: /raise stealth/i }));
      act(() => {
        vi.runAllTimers();
      });
      expect(lastSavedSkills()).toEqual({ '1': 20, '2': 10 });
    });

    it("drops points in a Magic skill's specialization out of the next save", () => {
      const legacy: CharacterDraft = {
        ...draft,
        draft_data: { skills: { '1': 20, '3': 20 }, specializations: { '10': 10, '30': 10 } },
      };
      renderSkillsSection(legacy);

      // 20 on Blades + 10 on Fencing; the Magic skill and its specialization are free.
      expect(screen.getByText('30')).toBeInTheDocument();

      fireEvent.click(screen.getByRole('button', { name: /raise stealth/i }));
      act(() => {
        vi.runAllTimers();
      });
      expect(mockUpdateDraftMutate.mock.calls.at(-1)?.[0].data.draft_data.specializations).toEqual({
        '10': 10,
      });
    });

    it('drops Magic points loaded from the draft out of the next save', () => {
      const legacy: CharacterDraft = {
        ...draft,
        draft_data: { skills: { '1': 20, '3': 20 } },
      };
      renderSkillsSection(legacy);

      // The purse counts only the 20 spent on Blades, not the 20 in Occult.
      expect(screen.getByText('40')).toBeInTheDocument();

      fireEvent.click(screen.getByRole('button', { name: /raise stealth/i }));
      act(() => {
        vi.runAllTimers();
      });
      expect(lastSavedSkills()).toEqual({ '1': 20, '2': 10 });
    });
  });
});

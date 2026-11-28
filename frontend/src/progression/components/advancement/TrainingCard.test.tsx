/**
 * TrainingCard tests (#3045). Mocks `@/skills/queries` and
 * `@/roster/usePersonaSearch` (no msw) — mirrors MotifStylePanel.test.tsx's idiom.
 */

import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { toast } from 'sonner';
import { vi } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { TrainingCard } from './TrainingCard';
import type {
  useCreateTrainingAllocationMutation,
  useDeleteTrainingAllocationMutation,
  useSkillsCatalogQuery,
  useTrainingAllocationsQuery,
  useUpdateTrainingAllocationMutation,
} from '@/skills/queries';
import type { TrainingAllocation } from '@/skills/types';

vi.mock('@/skills/queries', () => ({
  useSkillsCatalogQuery: vi.fn(),
  useTrainingAllocationsQuery: vi.fn(),
  useCreateTrainingAllocationMutation: vi.fn(),
  useUpdateTrainingAllocationMutation: vi.fn(),
  useDeleteTrainingAllocationMutation: vi.fn(),
}));

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

vi.mock('@/roster/usePersonaSearch', () => ({
  usePersonaSearch: vi.fn(() => ({ results: [], isFetching: false })),
}));

import * as skillsQueries from '@/skills/queries';

const allocation: TrainingAllocation = {
  id: 7,
  skill: { id: 1, name: 'Swordplay', category: 'combat', category_display: 'Combat' },
  specialization: null as unknown as TrainingAllocation['specialization'],
  mentor: null as unknown as TrainingAllocation['mentor'],
  mentor_accepted_at: null,
  mentor_waiting: false,
  ap_amount: 2,
  remaining_weekly_budget: 3,
};

function setupMocks(options?: {
  allocations?: TrainingAllocation[];
  remaining?: number;
  isLoading?: boolean;
  catalog?: { id: number; name: string; category: string; category_display: string }[];
}) {
  const create = vi.fn();
  const update = vi.fn();
  const remove = vi.fn();

  vi.mocked(skillsQueries.useSkillsCatalogQuery).mockReturnValue({
    data: options?.catalog ?? [
      { id: 1, name: 'Swordplay', category: 'combat', category_display: 'Combat' },
    ],
  } as unknown as ReturnType<typeof useSkillsCatalogQuery>);

  vi.mocked(skillsQueries.useTrainingAllocationsQuery).mockReturnValue({
    data: {
      allocations: options?.allocations ?? [allocation],
      remaining_weekly_budget: options?.remaining ?? 3,
    },
    isLoading: options?.isLoading ?? false,
    error: null,
  } as unknown as ReturnType<typeof useTrainingAllocationsQuery>);

  vi.mocked(skillsQueries.useCreateTrainingAllocationMutation).mockReturnValue({
    mutate: create,
    isPending: false,
  } as unknown as ReturnType<typeof useCreateTrainingAllocationMutation>);

  vi.mocked(skillsQueries.useUpdateTrainingAllocationMutation).mockReturnValue({
    mutate: update,
    isPending: false,
  } as unknown as ReturnType<typeof useUpdateTrainingAllocationMutation>);

  vi.mocked(skillsQueries.useDeleteTrainingAllocationMutation).mockReturnValue({
    mutate: remove,
    isPending: false,
    variables: undefined,
  } as unknown as ReturnType<typeof useDeleteTrainingAllocationMutation>);

  return { create, update, remove };
}

describe('TrainingCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the remaining weekly AP budget', () => {
    setupMocks({ remaining: 5 });
    renderWithProviders(<TrainingCard />);
    expect(screen.getByText('5 AP remaining this week')).toBeInTheDocument();
  });

  it('renders an allocation row with skill name and self-study badge', () => {
    setupMocks();
    renderWithProviders(<TrainingCard />);
    const row = screen.getByTestId('training-allocation-row');
    expect(row).toHaveTextContent('Swordplay');
    expect(row).toHaveTextContent('Self-study');
  });

  it('shows the mentor name instead of self-study when a mentor is set', () => {
    setupMocks({
      allocations: [{ ...allocation, mentor: { id: 3, name: 'Elenna' } }],
    });
    renderWithProviders(<TrainingCard />);
    expect(screen.getByTestId('training-allocation-row')).toHaveTextContent('Mentor: Elenna');
  });

  it('says a named mentor has not agreed yet while the allocation is waiting', () => {
    setupMocks({
      allocations: [{ ...allocation, mentor: { id: 3, name: 'Drusa Kell' }, mentor_waiting: true }],
    });
    renderWithProviders(<TrainingCard />);
    expect(screen.getByTestId('training-mentor-line')).toHaveTextContent(
      'Mentor: Drusa Kell · waiting for Drusa Kell to agree'
    );
  });

  it('shows an agreed mentor with no waiting note', () => {
    setupMocks({
      allocations: [
        {
          ...allocation,
          mentor: { id: 3, name: 'Drusa Kell' },
          mentor_accepted_at: '2026-11-28T10:00:00Z',
          mentor_waiting: false,
        },
      ],
    });
    renderWithProviders(<TrainingCard />);
    const line = screen.getByTestId('training-mentor-line');
    expect(line).toHaveTextContent('Mentor: Drusa Kell');
    expect(line).not.toHaveTextContent('waiting');
  });

  it('tells the student the mentor has been asked once a waiting allocation is saved', async () => {
    const { create } = setupMocks();
    create.mockImplementation(
      (_body: unknown, opts: { onSuccess: (created: TrainingAllocation) => void }) =>
        opts.onSuccess({
          ...allocation,
          mentor: { id: 3, name: 'Drusa Kell' },
          mentor_waiting: true,
        })
    );
    renderWithProviders(<TrainingCard />);

    await userEvent.selectOptions(screen.getByTestId('training-skill-select'), '1');
    await userEvent.click(screen.getByTestId('training-add-submit'));

    expect(toast.success).toHaveBeenCalledWith('Training allocated. Drusa Kell has been asked.');
  });

  it('shows the empty state when nothing is allocated', () => {
    setupMocks({ allocations: [] });
    renderWithProviders(<TrainingCard />);
    expect(screen.getByTestId('training-empty')).toBeInTheDocument();
  });

  it('Remove dispatches the delete mutation with the allocation id', async () => {
    const { remove } = setupMocks();
    renderWithProviders(<TrainingCard />);

    await userEvent.click(screen.getByTestId('training-remove-7'));

    expect(remove).toHaveBeenCalledWith(7, expect.anything());
  });

  it('editing the AP input on blur dispatches the update mutation', async () => {
    const { update } = setupMocks();
    renderWithProviders(<TrainingCard />);

    const input = screen.getByTestId('training-ap-input-7');
    await userEvent.clear(input);
    await userEvent.type(input, '4');
    await userEvent.tab();

    expect(update).toHaveBeenCalledWith({ id: 7, body: { ap_amount: 4 } }, expect.anything());
  });

  it('submitting the add form dispatches the create mutation with skill_id and ap_amount', async () => {
    const { create } = setupMocks();
    renderWithProviders(<TrainingCard />);

    await userEvent.selectOptions(screen.getByTestId('training-skill-select'), '1');
    const apInput = screen.getByLabelText('AP');
    await userEvent.clear(apInput);
    await userEvent.type(apInput, '3');
    await userEvent.click(screen.getByTestId('training-add-submit'));

    expect(create).toHaveBeenCalledWith(
      { skill_id: 1, ap_amount: 3, mentor_persona_id: undefined },
      expect.anything()
    );
  });

  it('disables the add-submit button until a skill is chosen', () => {
    setupMocks();
    renderWithProviders(<TrainingCard />);
    expect(screen.getByTestId('training-add-submit')).toBeDisabled();
  });

  describe('a magical skill needs a mentor (#5326)', () => {
    const catalog = [
      { id: 1, name: 'Swordplay', category: 'combat', category_display: 'Combat' },
      { id: 14, name: 'Villainy', category: 'magic', category_display: 'Magic' },
    ];

    it('labels the mentor field required once a magical skill is chosen', async () => {
      setupMocks({ catalog });
      renderWithProviders(<TrainingCard />);

      expect(screen.getByText('Mentor')).toBeInTheDocument();
      expect(screen.getByPlaceholderText('Mentor (optional)…')).toBeInTheDocument();

      await userEvent.selectOptions(screen.getByTestId('training-skill-select'), '14');

      expect(screen.getByText('Mentor (required)')).toBeInTheDocument();
      expect(screen.getByPlaceholderText('Mentor (required)…')).toBeInTheDocument();
      expect(screen.getByTestId('training-add-submit')).toBeEnabled();
    });

    it('keeps the mentor field optional for a skill that is not magical', async () => {
      setupMocks({ catalog });
      renderWithProviders(<TrainingCard />);

      await userEvent.selectOptions(screen.getByTestId('training-skill-select'), '1');

      expect(screen.getByText('Mentor')).toBeInTheDocument();
      expect(screen.getByPlaceholderText('Mentor (optional)…')).toBeInTheDocument();
    });

    it('shows the optional label again when the skill changes back', async () => {
      setupMocks({ catalog });
      renderWithProviders(<TrainingCard />);

      await userEvent.selectOptions(screen.getByTestId('training-skill-select'), '14');
      await userEvent.selectOptions(screen.getByTestId('training-skill-select'), '1');

      expect(screen.getByPlaceholderText('Mentor (optional)…')).toBeInTheDocument();
    });

    it("shows the server's refusal text in the error toast", async () => {
      const refusal = 'Villainy needs a teacher. Choose a mentor whose Tradition teaches it.';
      const { create } = setupMocks({ catalog });
      create.mockImplementation((_body: unknown, opts: { onError: (e: unknown) => void }) =>
        opts.onError(new Error(refusal))
      );
      renderWithProviders(<TrainingCard />);

      await userEvent.selectOptions(screen.getByTestId('training-skill-select'), '14');
      await userEvent.click(screen.getByTestId('training-add-submit'));

      expect(toast.error).toHaveBeenCalledWith(refusal);
    });
  });
});

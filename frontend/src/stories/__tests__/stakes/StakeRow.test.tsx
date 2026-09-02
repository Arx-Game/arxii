/**
 * StakeRow tests (#3561).
 */

import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { StakeRow } from '../../components/stakes/StakeRow';
import { makeBeat, makeStake, makeTemplate } from './fixtures';

vi.mock('../../queries', () => ({
  useUpdateStake: vi.fn(),
  useDeleteStake: vi.fn(),
  useStakeTemplates: vi.fn(),
}));

vi.mock('../../components/SubjectRefFields', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../components/SubjectRefFields')>();
  return {
    ...actual,
    SubjectRefFields: ({ value }: { value: { subject_kind: string } }) => (
      <div data-testid="stub-subject-ref-fields">{value.subject_kind}</div>
    ),
  };
});

vi.mock('../../components/stakes/BranchColumns', () => ({
  BranchColumns: ({ stake }: { stake: { id: number } }) => (
    <div data-testid={`stub-branch-columns-${stake.id}`}>branch columns</div>
  ),
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

import * as queries from '../../queries';

function mockTemplates(results: ReturnType<typeof makeTemplate>[]) {
  vi.mocked(queries.useStakeTemplates).mockReturnValue({
    data: { count: results.length, next: null, previous: null, results },
    isLoading: false,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  } as any);
}

function makeMutationMocks() {
  const update = vi.fn();
  const del = vi.fn();
  vi.mocked(queries.useUpdateStake).mockReturnValue({
    mutate: update,
    isPending: false,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  } as any);
  vi.mocked(queries.useDeleteStake).mockReturnValue({
    mutate: del,
    isPending: false,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  } as any);
  return { update, del };
}

describe('StakeRow', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows the template name read-only and mounts BranchColumns', () => {
    mockTemplates([makeTemplate({ id: 5, name: 'Courtly disfavor' })]);
    makeMutationMocks();
    const stake = makeStake({ template: 5 });

    renderWithProviders(<StakeRow stake={stake} beat={makeBeat()} />);

    expect(screen.getByTestId(`stake-template-${stake.id}`)).toHaveTextContent('Courtly disfavor');
    expect(screen.getByTestId(`stub-branch-columns-${stake.id}`)).toBeInTheDocument();
  });

  it('shows "Custom stake" when the stake has no template', () => {
    mockTemplates([]);
    makeMutationMocks();
    const stake = makeStake({ template: null });

    renderWithProviders(<StakeRow stake={stake} beat={makeBeat()} />);

    expect(screen.getByTestId(`stake-template-${stake.id}`)).toHaveTextContent('Custom stake');
  });

  it('Save sends the severity and player summary edits', async () => {
    const user = userEvent.setup();
    mockTemplates([]);
    const { update } = makeMutationMocks();
    const stake = makeStake({ severity: 1, player_summary: 'Old summary' });
    const beat = makeBeat();

    renderWithProviders(<StakeRow stake={stake} beat={beat} />);

    await user.selectOptions(screen.getByTestId(`stake-severity-${stake.id}`), '4');
    await user.clear(screen.getByTestId(`stake-player-summary-${stake.id}`));
    await user.type(screen.getByTestId(`stake-player-summary-${stake.id}`), 'New summary');
    await user.click(screen.getByTestId(`stake-save-${stake.id}`));

    expect(update).toHaveBeenCalledWith(
      expect.objectContaining({
        id: stake.id,
        beatId: beat.id,
        severity: 4,
        player_summary: 'New summary',
      }),
      expect.anything()
    );
  });

  it('Delete confirms then calls the delete mutation', async () => {
    const user = userEvent.setup();
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    mockTemplates([]);
    const { del } = makeMutationMocks();
    const stake = makeStake();
    const beat = makeBeat();

    renderWithProviders(<StakeRow stake={stake} beat={beat} />);
    await user.click(screen.getByTestId(`stake-delete-${stake.id}`));

    expect(del).toHaveBeenCalledWith({ id: stake.id, beatId: beat.id }, expect.anything());
  });

  it('disables Save/Delete when disabled (locked)', () => {
    mockTemplates([]);
    makeMutationMocks();
    const stake = makeStake();

    renderWithProviders(<StakeRow stake={stake} beat={makeBeat()} disabled />);

    expect(screen.getByTestId(`stake-save-${stake.id}`)).toBeDisabled();
    expect(screen.getByTestId(`stake-delete-${stake.id}`)).toBeDisabled();
  });
});

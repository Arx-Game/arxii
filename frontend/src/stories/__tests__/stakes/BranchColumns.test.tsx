/**
 * BranchColumns tests (#3561).
 */

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { BranchColumns } from '../../components/stakes/BranchColumns';
import { makeBeat, makeResolution, makeStake } from './fixtures';
import { toast } from 'sonner';

vi.mock('../../queries', () => ({
  useStakeResolutions: vi.fn(),
  useCreateStakeResolution: vi.fn(),
  useUpdateStakeResolution: vi.fn(),
  useDeleteStakeResolution: vi.fn(),
}));

vi.mock('../../components/ConsequencePoolPicker', () => ({
  ConsequencePoolPicker: ({ label }: { label: string }) => <div>{label}</div>,
}));

vi.mock('../../components/stakes/RewardLinesEditor', () => ({
  RewardLinesEditor: ({ resolutionId }: { resolutionId: number }) => (
    <div data-testid={`stub-reward-lines-${resolutionId}`}>reward lines</div>
  ),
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

import * as queries from '../../queries';

function mockResolutions(results: ReturnType<typeof makeResolution>[]) {
  vi.mocked(queries.useStakeResolutions).mockReturnValue({
    data: { count: results.length, next: null, previous: null, results },
    isLoading: false,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  } as any);
}

function makeMutationMocks() {
  const create = vi.fn();
  const update = vi.fn();
  const del = vi.fn();
  vi.mocked(queries.useCreateStakeResolution).mockReturnValue({
    mutate: create,
    isPending: false,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  } as any);
  vi.mocked(queries.useUpdateStakeResolution).mockReturnValue({
    mutate: update,
    isPending: false,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  } as any);
  vi.mocked(queries.useDeleteStakeResolution).mockReturnValue({
    mutate: del,
    isPending: false,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  } as any);
  return { create, update, del };
}

describe('BranchColumns', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('groups authored branches into WIN / LOSS / WITHDRAWAL columns', () => {
    mockResolutions([
      makeResolution({ id: 1, column: 'win', outcome_key: '' }),
      makeResolution({ id: 2, column: 'win', outcome_key: 'given_to_allies' }),
      makeResolution({ id: 3, column: 'loss' }),
      makeResolution({ id: 4, column: 'withdrawal' }),
    ]);
    makeMutationMocks();
    const stake = makeStake();
    const beat = makeBeat();

    renderWithProviders(<BranchColumns stake={stake} beat={beat} />);

    expect(
      within(screen.getByTestId('branch-column-win')).getByTestId('branch-card-1')
    ).toBeInTheDocument();
    expect(
      within(screen.getByTestId('branch-column-win')).getByTestId('branch-card-2')
    ).toBeInTheDocument();
    expect(
      within(screen.getByTestId('branch-column-loss')).getByTestId('branch-card-3')
    ).toBeInTheDocument();
    expect(
      within(screen.getByTestId('branch-column-withdrawal')).getByTestId('branch-card-4')
    ).toBeInTheDocument();
    // Reward lines only mount on the WIN column.
    expect(screen.getByTestId('stub-reward-lines-1')).toBeInTheDocument();
    expect(screen.queryByTestId('stub-reward-lines-3')).not.toBeInTheDocument();
  });

  it('an ITEM branch save sends forfeits_subject_item and never NPC fields', async () => {
    const user = userEvent.setup();
    mockResolutions([makeResolution({ id: 1, column: 'loss' })]);
    const { update } = makeMutationMocks();
    const stake = makeStake({ subject_kind: 'item' });
    const beat = makeBeat();

    renderWithProviders(<BranchColumns stake={stake} beat={beat} />);

    await user.click(screen.getByTestId('branch-forfeits-item-1'));
    await user.click(screen.getByTestId('branch-save-1'));

    expect(update).toHaveBeenCalledTimes(1);
    const [payload] = update.mock.calls[0];
    expect(payload).toMatchObject({
      id: 1,
      stakeId: stake.id,
      beatId: beat.id,
      forfeits_subject_item: true,
    });
    expect(payload).not.toHaveProperty('sets_subject_lifecycle');
    expect(payload).not.toHaveProperty('subject_standing_delta');
    expect(payload).not.toHaveProperty('npc_regard_delta');
    expect(payload).not.toHaveProperty('machine_match_lifecycle_state');
  });

  it('an NPC_FATE branch save sends the four NPC fields', async () => {
    const user = userEvent.setup();
    mockResolutions([makeResolution({ id: 1, column: 'loss' })]);
    const { update } = makeMutationMocks();
    const stake = makeStake({ subject_kind: 'npc_fate' });
    const beat = makeBeat();

    renderWithProviders(<BranchColumns stake={stake} beat={beat} />);

    await user.selectOptions(screen.getByTestId('branch-sets-lifecycle-1'), 'DEAD');
    await user.click(screen.getByTestId('branch-save-1'));

    expect(update).toHaveBeenCalledTimes(1);
    const [payload] = update.mock.calls[0];
    expect(payload).toMatchObject({
      id: 1,
      stakeId: stake.id,
      beatId: beat.id,
      sets_subject_lifecycle: 'DEAD',
      subject_standing_delta: 0,
      npc_regard_delta: 0,
      machine_match_lifecycle_state: '',
    });
    expect(payload).not.toHaveProperty('forfeits_subject_item');
    expect(payload).not.toHaveProperty('transitions_subject_asset');
  });

  it('"Add default branch" is hidden once a blank-outcome_key branch exists', () => {
    mockResolutions([makeResolution({ id: 1, column: 'win', outcome_key: '' })]);
    makeMutationMocks();

    renderWithProviders(<BranchColumns stake={makeStake()} beat={makeBeat()} />);

    expect(screen.queryByTestId('add-default-branch-win')).not.toBeInTheDocument();
    expect(screen.getByTestId('add-default-branch-loss')).toBeInTheDocument();
  });

  it('named-branch key select offers the beat scenario option keys', async () => {
    const user = userEvent.setup();
    mockResolutions([]);
    const { create } = makeMutationMocks();
    const beat = makeBeat({
      scenario: { template_id: 9, name: 'The Heist', option_keys: ['sabotage', 'diplomacy'] },
    });

    renderWithProviders(<BranchColumns stake={makeStake()} beat={beat} />);

    await user.click(screen.getByTestId('add-named-branch-win'));
    const select = screen.getByTestId('named-branch-key-select-win');
    expect(within(select).getByText('sabotage')).toBeInTheDocument();
    expect(within(select).getByText('diplomacy')).toBeInTheDocument();

    await user.selectOptions(select, 'sabotage');
    await user.click(screen.getByTestId('confirm-named-branch-win'));

    expect(create).toHaveBeenCalledWith(
      { beatId: beat.id, stake: makeStake().id, column: 'win', outcome_key: 'sabotage' },
      expect.anything()
    );
  });

  it('named-branch key is free text when the beat has no scenario', async () => {
    const user = userEvent.setup();
    mockResolutions([]);
    makeMutationMocks();
    const beat = makeBeat({ scenario: null });

    renderWithProviders(<BranchColumns stake={makeStake()} beat={beat} />);

    await user.click(screen.getByTestId('add-named-branch-loss'));
    expect(screen.getByTestId('named-branch-key-input-loss')).toBeInTheDocument();
    expect(screen.queryByTestId('named-branch-key-select-loss')).not.toBeInTheDocument();
  });

  it('disables Add and warns when the chosen named-branch key already exists on that column', async () => {
    const user = userEvent.setup();
    mockResolutions([makeResolution({ id: 1, column: 'loss', outcome_key: 'surrendered' })]);
    makeMutationMocks();
    const beat = makeBeat({ scenario: null });

    renderWithProviders(<BranchColumns stake={makeStake()} beat={beat} />);

    await user.click(screen.getByTestId('add-named-branch-loss'));
    await user.type(screen.getByTestId('named-branch-key-input-loss'), 'surrendered');

    expect(screen.getByTestId('named-branch-key-duplicate-loss')).toHaveTextContent(
      'That key is already authored on this column'
    );
    expect(screen.getByTestId('confirm-named-branch-loss')).toBeDisabled();
  });

  it('surfaces the mutation error message on a rejected branch save', async () => {
    const user = userEvent.setup();
    mockResolutions([makeResolution({ id: 1, column: 'loss' })]);
    const { update } = makeMutationMocks();
    update.mockImplementation((_vars, opts) => {
      opts.onError(new Error('column LOSS already has branch "surrendered"'));
    });

    renderWithProviders(<BranchColumns stake={makeStake()} beat={makeBeat()} />);
    await user.click(screen.getByTestId('branch-save-1'));

    expect(toast.error).toHaveBeenCalledWith('column LOSS already has branch "surrendered"');
  });
});

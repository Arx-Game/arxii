/**
 * RewardLinesEditor tests (#3561).
 */

import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { RewardLinesEditor } from '../../components/stakes/RewardLinesEditor';
import { makeRewardLine } from './fixtures';
import { toast } from 'sonner';

vi.mock('../../queries', () => ({
  useStakeRewardLines: vi.fn(),
  useCreateStakeRewardLine: vi.fn(),
  useUpdateStakeRewardLine: vi.fn(),
  useDeleteStakeRewardLine: vi.fn(),
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

import * as queries from '../../queries';

function mockLines(results: ReturnType<typeof makeRewardLine>[]) {
  vi.mocked(queries.useStakeRewardLines).mockReturnValue({
    data: { count: results.length, next: null, previous: null, results },
    isLoading: false,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  } as any);
}

function makeMutationMocks() {
  const create = vi.fn();
  const update = vi.fn();
  const del = vi.fn();
  vi.mocked(queries.useCreateStakeRewardLine).mockReturnValue({
    mutate: create,
    isPending: false,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  } as any);
  vi.mocked(queries.useUpdateStakeRewardLine).mockReturnValue({
    mutate: update,
    isPending: false,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  } as any);
  vi.mocked(queries.useDeleteStakeRewardLine).mockReturnValue({
    mutate: del,
    isPending: false,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  } as any);
  return { create, update, del };
}

describe('RewardLinesEditor', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders existing reward lines from fixtures', () => {
    mockLines([makeRewardLine({ id: 1, sink: 'money', amount: 25 })]);
    makeMutationMocks();

    renderWithProviders(<RewardLinesEditor resolutionId={30} beatId={200} />);

    expect(screen.getByTestId('reward-line-row-1')).toBeInTheDocument();
    expect(screen.getByTestId('reward-line-amount-1')).toHaveValue(25);
  });

  it('shows an empty state with no reward lines', () => {
    mockLines([]);
    makeMutationMocks();

    renderWithProviders(<RewardLinesEditor resolutionId={30} beatId={200} />);

    expect(screen.getByText(/No reward lines authored yet/)).toBeInTheDocument();
  });

  it('"Add reward line" sends {resolution, sink, amount} with beatId', async () => {
    const user = userEvent.setup();
    mockLines([]);
    const { create } = makeMutationMocks();

    renderWithProviders(<RewardLinesEditor resolutionId={30} beatId={200} />);
    await user.click(screen.getByTestId('reward-line-add-30'));

    expect(create).toHaveBeenCalledWith(
      { beatId: 200, resolution: 30, sink: 'money', amount: 1 },
      expect.anything()
    );
  });

  it('reveals a resonance id field only when sink is resonance, and Save includes it', async () => {
    const user = userEvent.setup();
    mockLines([makeRewardLine({ id: 2, sink: 'money', amount: 5, resonance: null })]);
    const { update } = makeMutationMocks();

    renderWithProviders(<RewardLinesEditor resolutionId={30} beatId={200} />);

    expect(screen.queryByTestId('reward-line-resonance-2')).not.toBeInTheDocument();

    await user.selectOptions(screen.getByTestId('reward-line-sink-2'), 'resonance');
    expect(screen.getByTestId('reward-line-resonance-2')).toBeInTheDocument();

    await user.type(screen.getByTestId('reward-line-resonance-2'), '7');
    await user.click(screen.getByTestId('reward-line-save-2'));

    expect(update).toHaveBeenCalledWith(
      { id: 2, resolutionId: 30, beatId: 200, sink: 'resonance', amount: 5, resonance: 7 },
      expect.anything()
    );
  });

  it('surfaces the mutation error message on a rejected add', async () => {
    const user = userEvent.setup();
    mockLines([]);
    const { create } = makeMutationMocks();
    create.mockImplementation((_vars, opts) => {
      opts.onError(new Error('column LOSS already has branch "surrendered"'));
    });

    renderWithProviders(<RewardLinesEditor resolutionId={30} beatId={200} />);
    await user.click(screen.getByTestId('reward-line-add-30'));

    expect(toast.error).toHaveBeenCalledWith('column LOSS already has branch "surrendered"');
  });

  it('Remove calls the delete mutation after confirm', async () => {
    const user = userEvent.setup();
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    mockLines([makeRewardLine({ id: 3 })]);
    const { del } = makeMutationMocks();

    renderWithProviders(<RewardLinesEditor resolutionId={30} beatId={200} />);
    await user.click(screen.getByTestId('reward-line-remove-3'));

    expect(del).toHaveBeenCalledWith({ id: 3, resolutionId: 30, beatId: 200 }, expect.anything());
  });
});

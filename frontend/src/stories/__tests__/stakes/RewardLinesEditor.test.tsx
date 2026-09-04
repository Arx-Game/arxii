/**
 * RewardLinesEditor tests (#3561; item/clue/codex pickers #3566).
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

vi.mock('../../api', () => ({
  searchItemTemplates: vi.fn().mockResolvedValue([]),
  resolveItemTemplateById: vi.fn().mockResolvedValue(null),
  searchClues: vi.fn().mockResolvedValue([]),
  searchCodexEntries: vi.fn().mockResolvedValue([]),
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

import * as queries from '../../queries';
import * as api from '../../api';

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
      {
        id: 2,
        resolutionId: 30,
        beatId: 200,
        sink: 'resonance',
        amount: 5,
        resonance: 7,
        item_template: null,
        clue: null,
        codex_entry: null,
      },
      expect.anything()
    );
  });

  it('MONEY Save is unchanged apart from the null item/clue/codex FKs', async () => {
    const user = userEvent.setup();
    mockLines([makeRewardLine({ id: 6, sink: 'money', amount: 5 })]);
    const { update } = makeMutationMocks();

    renderWithProviders(<RewardLinesEditor resolutionId={30} beatId={200} />);

    await user.clear(screen.getByTestId('reward-line-amount-6'));
    await user.type(screen.getByTestId('reward-line-amount-6'), '12');
    await user.click(screen.getByTestId('reward-line-save-6'));

    expect(update).toHaveBeenCalledWith(
      {
        id: 6,
        resolutionId: 30,
        beatId: 200,
        sink: 'money',
        amount: 12,
        resonance: null,
        item_template: null,
        clue: null,
        codex_entry: null,
      },
      expect.anything()
    );
  });

  it('ITEM sink shows the picker and a read-only amount; Save omits amount', async () => {
    const user = userEvent.setup();
    vi.mocked(api.searchItemTemplates).mockResolvedValue([
      { id: 12, name: 'Rusty Blade', hint: '40' },
    ]);
    mockLines([makeRewardLine({ id: 7, sink: 'money', amount: 5 })]);
    const { update } = makeMutationMocks();

    renderWithProviders(<RewardLinesEditor resolutionId={30} beatId={200} />);

    await user.selectOptions(screen.getByTestId('reward-line-sink-7'), 'item');
    expect(screen.getByTestId('reward-line-amount-7')).toHaveTextContent('Amount:');

    const itemInput = screen.getByLabelText(/item template/i);
    await user.type(itemInput, 'Rusty');
    await user.click(await screen.findByText('Rusty Blade'));
    expect(screen.getByTestId('reward-line-amount-7')).toHaveTextContent('Amount: 40');

    await user.click(screen.getByTestId('reward-line-save-7'));

    expect(update).toHaveBeenCalledWith(
      {
        id: 7,
        resolutionId: 30,
        beatId: 200,
        sink: 'item',
        resonance: null,
        item_template: 12,
        clue: null,
        codex_entry: null,
      },
      expect.anything()
    );
  });

  it('CLUE Save sends the picked clue id with the typed amount', async () => {
    const user = userEvent.setup();
    vi.mocked(api.searchClues).mockResolvedValue([
      { id: 9, name: 'A torn letter', hint: 'npc_regard' },
    ]);
    mockLines([makeRewardLine({ id: 8, sink: 'money', amount: 5 })]);
    const { update } = makeMutationMocks();

    renderWithProviders(<RewardLinesEditor resolutionId={30} beatId={200} />);

    await user.selectOptions(screen.getByTestId('reward-line-sink-8'), 'clue');
    const clueInput = screen.getByLabelText(/^clue$/i);
    await user.type(clueInput, 'torn');
    await user.click(await screen.findByText('A torn letter'));

    await user.clear(screen.getByTestId('reward-line-amount-8'));
    await user.type(screen.getByTestId('reward-line-amount-8'), '3');
    await user.click(screen.getByTestId('reward-line-save-8'));

    expect(update).toHaveBeenCalledWith(
      {
        id: 8,
        resolutionId: 30,
        beatId: 200,
        sink: 'clue',
        amount: 3,
        resonance: null,
        item_template: null,
        clue: 9,
        codex_entry: null,
      },
      expect.anything()
    );
  });

  it('CODEX Save sends the picked codex entry id with the typed amount', async () => {
    const user = userEvent.setup();
    vi.mocked(api.searchCodexEntries).mockResolvedValue([{ id: 4, name: 'The Sundering' }]);
    mockLines([makeRewardLine({ id: 9, sink: 'money', amount: 5 })]);
    const { update } = makeMutationMocks();

    renderWithProviders(<RewardLinesEditor resolutionId={30} beatId={200} />);

    await user.selectOptions(screen.getByTestId('reward-line-sink-9'), 'codex');
    const codexInput = screen.getByLabelText(/codex entry/i);
    await user.type(codexInput, 'Sunder');
    await user.click(await screen.findByText('The Sundering'));

    await user.clear(screen.getByTestId('reward-line-amount-9'));
    await user.type(screen.getByTestId('reward-line-amount-9'), '1');
    await user.click(screen.getByTestId('reward-line-save-9'));

    expect(update).toHaveBeenCalledWith(
      {
        id: 9,
        resolutionId: 30,
        beatId: 200,
        sink: 'codex',
        amount: 1,
        resonance: null,
        item_template: null,
        clue: null,
        codex_entry: 4,
      },
      expect.anything()
    );
  });

  it('renders the readonly name field for an existing ITEM reward line', () => {
    mockLines([
      makeRewardLine({
        id: 10,
        sink: 'item',
        amount: 40,
        item_template: 12,
        item_template_name: 'Rusty Blade',
      }),
    ]);
    makeMutationMocks();

    renderWithProviders(<RewardLinesEditor resolutionId={30} beatId={200} />);

    expect(screen.getByText('Current: Rusty Blade')).toBeInTheDocument();
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

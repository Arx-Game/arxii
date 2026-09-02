/**
 * StakesPanel tests (#3561).
 */

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { StakesPanel } from '../../components/stakes/StakesPanel';
import { makeBeat, makeStake, makeTemplate } from './fixtures';
import { toast } from 'sonner';

vi.mock('../../queries', () => ({
  useStakes: vi.fn(),
  useOpenBeatActivation: vi.fn(),
  useStakeTemplates: vi.fn(),
  useCreateStake: vi.fn(),
  useBeatReadiness: vi.fn(),
}));

vi.mock('@/gm/queries', () => ({
  useGMProfileMine: vi.fn(),
}));

let accountState = { is_staff: false };

vi.mock('@/store/hooks', () => ({
  useAccount: vi.fn(() => ({
    id: 1,
    username: 'testuser',
    is_staff: accountState.is_staff,
    available_characters: [],
  })),
}));

vi.mock('../../components/stakes/StakeRow', () => ({
  StakeRow: ({ stake }: { stake: { id: number } }) => (
    <li data-testid={`stub-stake-row-${stake.id}`}>stake row</li>
  ),
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

import * as queries from '../../queries';
import * as gmQueries from '@/gm/queries';

function mockStakes(results: ReturnType<typeof makeStake>[]) {
  vi.mocked(queries.useStakes).mockReturnValue({
    data: { count: results.length, next: null, previous: null, results },
    isLoading: false,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  } as any);
}

function mockActivation(data: unknown) {
  vi.mocked(queries.useOpenBeatActivation).mockReturnValue({
    data,
    isLoading: false,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  } as any);
}

function mockTemplates(results: ReturnType<typeof makeTemplate>[]) {
  vi.mocked(queries.useStakeTemplates).mockReturnValue({
    data: { count: results.length, next: null, previous: null, results },
    isLoading: false,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  } as any);
}

function mockGMProfile(data: unknown) {
  vi.mocked(gmQueries.useGMProfileMine).mockReturnValue({
    data,
    isLoading: false,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  } as any);
}

function setupDefaults() {
  mockStakes([]);
  mockActivation(undefined);
  mockTemplates([]);
  mockGMProfile(null);
  vi.mocked(queries.useBeatReadiness).mockReturnValue({
    data: undefined,
    isLoading: false,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  } as any);
  vi.mocked(queries.useCreateStake).mockReturnValue({
    mutate: vi.fn(),
    isPending: false,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  } as any);
}

describe('StakesPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    accountState = { is_staff: false };
    setupDefaults();
  });

  it('renders one row per fixture stake', () => {
    mockStakes([makeStake({ id: 1 }), makeStake({ id: 2 })]);

    renderWithProviders(<StakesPanel beat={makeBeat()} />);

    expect(screen.getByTestId('stub-stake-row-1')).toBeInTheDocument();
    expect(screen.getByTestId('stub-stake-row-2')).toBeInTheDocument();
  });

  it('shows an empty state with no stakes', () => {
    renderWithProviders(<StakesPanel beat={makeBeat()} />);
    expect(screen.getByTestId('stakes-empty')).toBeInTheDocument();
  });

  it('hides the custom-stake button when the caller has no cap and is not staff', () => {
    mockGMProfile({ id: 1, level: 'JUNIOR', max_beat_risk: 'low', allow_custom_stakes: false });

    renderWithProviders(<StakesPanel beat={makeBeat()} />);

    expect(screen.getByTestId('stakes-add-btn')).toBeInTheDocument();
    expect(screen.queryByTestId('stakes-add-custom-btn')).not.toBeInTheDocument();
  });

  it('shows the custom-stake button when allow_custom_stakes is set', () => {
    mockGMProfile({ id: 1, level: 'SENIOR', max_beat_risk: 'extreme', allow_custom_stakes: true });

    renderWithProviders(<StakesPanel beat={makeBeat()} />);

    expect(screen.getByTestId('stakes-add-custom-btn')).toBeInTheDocument();
  });

  it('shows the custom-stake button for staff regardless of the cap', () => {
    accountState = { is_staff: true };
    mockGMProfile(null);

    renderWithProviders(<StakesPanel beat={makeBeat()} />);

    expect(screen.getByTestId('stakes-add-custom-btn')).toBeInTheDocument();
  });

  it('disables adding stakes while the contract is locked', () => {
    mockActivation([{ id: 1, beat: 200, locked_at: '2026-09-01T00:00:00Z' }]);
    mockGMProfile({ id: 1, level: 'SENIOR', max_beat_risk: 'extreme', allow_custom_stakes: true });

    renderWithProviders(<StakesPanel beat={makeBeat()} />);

    expect(screen.queryByTestId('stakes-add-btn')).not.toBeInTheDocument();
    expect(screen.queryByTestId('stakes-add-custom-btn')).not.toBeInTheDocument();
  });

  it('filters the template select to the beat risk band and creates a stake', async () => {
    const user = userEvent.setup();
    const createMutate = vi.fn();
    vi.mocked(queries.useCreateStake).mockReturnValue({
      mutate: createMutate,
      isPending: false,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } as any);
    mockTemplates([
      makeTemplate({ id: 1, name: 'In band', min_risk: 'low', max_risk: 'high' }),
      makeTemplate({ id: 2, name: 'Out of band', min_risk: 'extreme', max_risk: 'extreme' }),
    ]);
    const beat = makeBeat({ id: 200, risk: 'moderate' });

    renderWithProviders(<StakesPanel beat={beat} />);
    await user.click(screen.getByTestId('stakes-add-btn'));

    const select = screen.getByTestId('stakes-add-template-select');
    expect(within(select).getByText('In band')).toBeInTheDocument();
    expect(within(select).queryByText('Out of band')).not.toBeInTheDocument();

    await user.selectOptions(select, '1');
    await user.type(screen.getByTestId('stakes-add-template-summary'), 'The town turns on them');
    await user.click(screen.getByTestId('stakes-add-template-confirm'));

    expect(createMutate).toHaveBeenCalledWith(
      {
        beatId: 200,
        beat: 200,
        template: 1,
        player_summary: 'The town turns on them',
      },
      expect.anything()
    );
  });

  it('surfaces the mutation error message on a rejected add-stake', async () => {
    const user = userEvent.setup();
    const createMutate = vi.fn((_vars, opts) => {
      opts.onError(new Error('column LOSS already has branch "surrendered"'));
    });
    vi.mocked(queries.useCreateStake).mockReturnValue({
      mutate: createMutate,
      isPending: false,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } as any);
    mockTemplates([makeTemplate({ id: 1, name: 'In band', min_risk: 'low', max_risk: 'high' })]);

    renderWithProviders(<StakesPanel beat={makeBeat({ id: 200, risk: 'moderate' })} />);
    await user.click(screen.getByTestId('stakes-add-btn'));
    await user.selectOptions(screen.getByTestId('stakes-add-template-select'), '1');
    await user.type(screen.getByTestId('stakes-add-template-summary'), 'The town turns on them');
    await user.click(screen.getByTestId('stakes-add-template-confirm'));

    expect(toast.error).toHaveBeenCalledWith('column LOSS already has branch "surrendered"');
  });
});

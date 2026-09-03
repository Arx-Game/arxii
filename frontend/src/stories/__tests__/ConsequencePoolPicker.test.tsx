/**
 * ConsequencePoolPicker Tests (#3562)
 *
 * Covers:
 *  - Renders a "None" sentinel plus every pool from the catalog
 *  - Selecting a pool calls onChange with its id
 *  - When a pool is selected, its resolved entries render (name, tier +
 *    success level, effect types, "may remove the character" flag)
 *  - `disabled` propagates to the select
 */

import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { ConsequencePoolPicker } from '../components/ConsequencePoolPicker';

vi.mock('../queries', () => ({
  useBeatConsequencePools: vi.fn(),
  useConsequencePoolDetail: vi.fn(),
}));

import * as queries from '../queries';

const pools = [
  { id: 7, name: 'Wild Magic Surge', description: 'Chaotic backlash.' },
  { id: 8, name: 'Blood Debt', description: 'A price paid in kind.' },
];

function mockPools(data: typeof pools = pools) {
  vi.mocked(queries.useBeatConsequencePools).mockReturnValue({
    data,
    isLoading: false,
    isError: false,
    error: null,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  } as any);
}

function mockDetail(data: unknown) {
  vi.mocked(queries.useConsequencePoolDetail).mockReturnValue({
    data,
    isLoading: false,
    isError: false,
    error: null,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  } as any);
}

describe('ConsequencePoolPicker', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders a None sentinel plus every catalog pool', () => {
    mockPools();
    mockDetail(undefined);
    renderWithProviders(<ConsequencePoolPicker value={null} onChange={vi.fn()} label="Success" />);

    const select = screen.getByLabelText('Success') as HTMLSelectElement;
    expect(select.value).toBe('');
    expect(screen.getByRole('option', { name: 'None' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'Wild Magic Surge' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'Blood Debt' })).toBeInTheDocument();
  });

  it('calls onChange with the selected pool id', async () => {
    const user = userEvent.setup();
    mockPools();
    mockDetail(undefined);
    const onChange = vi.fn();
    renderWithProviders(<ConsequencePoolPicker value={null} onChange={onChange} label="Success" />);

    await user.selectOptions(screen.getByLabelText('Success'), '7');
    expect(onChange).toHaveBeenCalledWith(7);
  });

  it('calls onChange with null when None is re-selected', async () => {
    const user = userEvent.setup();
    mockPools();
    mockDetail({ id: 7, name: 'Wild Magic Surge', description: '', entries: [] });
    const onChange = vi.fn();
    renderWithProviders(<ConsequencePoolPicker value={7} onChange={onChange} label="Success" />);

    await user.selectOptions(screen.getByLabelText('Success'), '');
    expect(onChange).toHaveBeenCalledWith(null);
  });

  it('renders the selected pool entries from the mocked detail', () => {
    mockPools();
    mockDetail({
      id: 7,
      name: 'Wild Magic Surge',
      description: '',
      entries: [
        {
          consequence_id: 1,
          name: 'Arcane Backlash',
          outcome_tier: { id: 1, name: 'Severe', success_level: -2 },
          effect_types: ['condition', 'injury'],
          character_loss: false,
        },
        {
          consequence_id: 2,
          name: 'Unmaking',
          outcome_tier: null,
          effect_types: [],
          character_loss: true,
        },
      ],
    });

    renderWithProviders(<ConsequencePoolPicker value={7} onChange={vi.fn()} label="Success" />);

    const list = screen.getByTestId('consequence-pool-entries-7');
    expect(list).toHaveTextContent('Arcane Backlash');
    expect(list).toHaveTextContent('Severe');
    expect(list).toHaveTextContent('success level -2');
    expect(list).toHaveTextContent('condition, injury');
    expect(list).toHaveTextContent('Unmaking');
    expect(list).toHaveTextContent('may remove the character');
  });

  it('does not render the entries preview when no pool is selected', () => {
    mockPools();
    mockDetail(undefined);
    renderWithProviders(<ConsequencePoolPicker value={null} onChange={vi.fn()} label="Success" />);

    expect(screen.queryByTestId(/consequence-pool-entries-/)).not.toBeInTheDocument();
  });

  it('disables the select when disabled is set', () => {
    mockPools();
    mockDetail(undefined);
    renderWithProviders(
      <ConsequencePoolPicker value={null} onChange={vi.fn()} label="Success" disabled />
    );

    expect(screen.getByLabelText('Success')).toBeDisabled();
  });
});

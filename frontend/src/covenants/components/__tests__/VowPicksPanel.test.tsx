import { fireEvent, render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { VowPickCatalog } from '../../api';

vi.mock('../../queries', () => ({
  useVowPicks: vi.fn(),
  useChooseVowPick: vi.fn(),
}));

import * as queries from '../../queries';
import { VowPicksPanel } from '../VowPicksPanel';

const CATALOG: VowPickCatalog = {
  membership_id: 7,
  covenant_id: 3,
  covenant: 'The Quicksilver Hall',
  vow: 'Quicksilver',
  vow_level: 2,
  levels: [
    {
      level: 1,
      is_open: true,
      budget: 4,
      spent: 4,
      left: 0,
      picks: [
        {
          id: 11,
          name: 'Strike from the Flank',
          description: 'Your cut lands harder on someone already busy with an ally.',
          price: 2,
          effects: ['+damage on your strikes'],
          limits: 'Target limit: an ally is engaging them, met 6 times in 10',
          chosen: true,
          locked_reason: '',
          choosable: false,
        },
        {
          id: 12,
          name: 'Light on Your Feet',
          description: '',
          price: 4,
          effects: [],
          limits: 'no limits',
          chosen: false,
          locked_reason: 'costs more than is left',
          choosable: false,
        },
      ],
    },
    {
      level: 2,
      is_open: true,
      budget: 4,
      spent: 3,
      left: 1,
      picks: [
        {
          id: 21,
          name: 'Read the Feint',
          description: 'You see the second blade coming.',
          price: 1,
          effects: [],
          limits: 'Target limit: a boss, met 3 times in 10',
          chosen: false,
          locked_reason: '',
          choosable: true,
        },
      ],
    },
    {
      level: 3,
      is_open: false,
      budget: 4,
      spent: 0,
      left: 4,
      picks: [
        {
          id: 31,
          name: 'Last Stand',
          description: '',
          price: 2,
          effects: [],
          limits: 'no limits',
          chosen: false,
          locked_reason: 'opens at vow level 3',
          choosable: false,
        },
      ],
    },
  ],
};

const mutate = vi.fn();

function mockQueries(data: VowPickCatalog[] | undefined) {
  vi.mocked(queries.useVowPicks).mockReturnValue({ data } as ReturnType<
    typeof queries.useVowPicks
  >);
  vi.mocked(queries.useChooseVowPick).mockReturnValue({
    mutate,
    isPending: false,
    isError: false,
    error: null,
  } as unknown as ReturnType<typeof queries.useChooseVowPick>);
}

function pickRow(name: string): HTMLElement {
  const row = screen.getByText(name).closest('[data-testid="vow-pick"]');
  if (!(row instanceof HTMLElement)) throw new Error(`no row for ${name}`);
  return row;
}

describe('VowPicksPanel', () => {
  beforeEach(() => {
    mutate.mockReset();
  });

  it('shows each level with its spend and every pick, the locked ones saying why', () => {
    mockQueries([CATALOG]);
    render(<VowPicksPanel sheetId={5} />);

    expect(screen.getByText('Quicksilver · vow picks')).toBeInTheDocument();
    expect(screen.getByText('Vow level 2')).toBeInTheDocument();
    expect(screen.getByText('4 of 4')).toBeInTheDocument();
    expect(screen.getByText('3 of 4')).toBeInTheDocument();
    expect(screen.getByText('opens at vow level 3')).toBeInTheDocument();
    expect(
      within(pickRow('Strike from the Flank')).getByText(
        '+damage on your strikes · Target limit: an ally is engaging them, met 6 times in 10'
      )
    ).toBeInTheDocument();
    expect(
      within(pickRow('Light on Your Feet')).getByText('no limits · costs more than is left')
    ).toBeInTheDocument();
    expect(pickRow('Last Stand')).toHaveClass('vowpicks-locked');
    expect(pickRow('Strike from the Flank')).toHaveClass('vowpicks-chosen');
    expect(screen.getAllByRole('button', { name: 'Choose' })).toHaveLength(1);
  });

  it('chooses an open pick in its covenant', () => {
    mockQueries([CATALOG]);
    render(<VowPicksPanel sheetId={5} />);

    fireEvent.click(within(pickRow('Read the Feint')).getByRole('button', { name: 'Choose' }));

    expect(mutate).toHaveBeenCalledWith(
      { covenantId: 3, pickId: 21 },
      expect.objectContaining({ onSuccess: expect.any(Function) })
    );
  });

  it('draws nothing for a character with no primary vow', () => {
    mockQueries([]);
    const { container } = render(<VowPicksPanel sheetId={5} />);

    expect(container).toBeEmptyDOMElement();
  });
});

import { readFileSync } from 'node:fs';
import * as path from 'node:path';
import { fileURLToPath } from 'node:url';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ReswearOptions, VowPickCatalog, VowPickEntry } from '../../api';

vi.mock('../../queries', () => ({
  useReswearOptions: vi.fn(),
  useReswearPick: vi.fn(),
}));

import * as queries from '../../queries';
import { ReswearDialog } from '../ReswearDialog';

function pick(id: number, name: string, price: number, chosen: boolean): VowPickEntry {
  return {
    id,
    vow: 'Quicksilver',
    name,
    description: '',
    price,
    effects: [],
    limits: 'no limits',
    chosen,
    locked_reason: '',
    choosable: false,
  };
}

// Level 1 is full: Strike from the Flank and Quick Recovery at 2 points each, of 4.
const CATALOG: VowPickCatalog = {
  membership_id: 7,
  covenant_id: 3,
  covenant: 'The Quicksilver Hall',
  vow: 'Quicksilver',
  vow_level: 2,
  vows: ['Quicksilver'],
  levels: [
    {
      level: 1,
      is_open: true,
      budget: 4,
      spent: 4,
      left: 0,
      picks: [
        pick(11, 'Strike from the Flank', 2, true),
        pick(12, 'Quick Recovery', 2, true),
        pick(13, 'Feint and Vanish', 2, false),
        pick(14, 'Light on Your Feet', 4, false),
      ],
    },
  ],
};

const OPTIONS: ReswearOptions = {
  ritual_id: 40,
  ap_cost: 3,
  anima_cost: 10,
  components: ['Token of the Vow'],
  component_ids: [88],
  unavailable_reason: '',
};

const mutate = vi.fn();
const onDone = vi.fn();
const onOpenChange = vi.fn();

function mockQueries(options: ReswearOptions | undefined, error: Error | null = null) {
  vi.mocked(queries.useReswearOptions).mockReturnValue({ data: options } as ReturnType<
    typeof queries.useReswearOptions
  >);
  vi.mocked(queries.useReswearPick).mockReturnValue({
    mutate,
    reset: vi.fn(),
    isPending: false,
    isError: error !== null,
    error,
  } as unknown as ReturnType<typeof queries.useReswearPick>);
}

function renderDialog() {
  return render(
    <ReswearDialog catalog={CATALOG} sheetId={5} open onOpenChange={onOpenChange} onDone={onDone} />
  );
}

function choice(name: string): HTMLElement {
  return screen.getByRole('button', { name: new RegExp(name) });
}

describe('ReswearDialog', () => {
  beforeEach(() => {
    mutate.mockReset();
    onDone.mockReset();
    onOpenChange.mockReset();
  });

  it('shows the swap, the level before and after, and the cost', () => {
    mockQueries(OPTIONS);
    renderDialog();

    fireEvent.click(choice('Quick Recovery'));

    expect(screen.getByText('Quicksilver · level 1')).toBeInTheDocument();
    expect(choice('Quick Recovery')).toHaveAttribute('aria-pressed', 'true');
    expect(choice('Feint and Vanish')).toHaveAttribute('aria-pressed', 'true');
    expect(choice('Light on Your Feet')).toBeDisabled();
    expect(screen.getByText('costs more than is left')).toBeInTheDocument();
    expect(screen.getByTestId('reswear-before')).toHaveTextContent(
      'Level 1 before4 of 4 · Strike from the Flank, Quick Recovery'
    );
    expect(screen.getByTestId('reswear-after')).toHaveTextContent(
      'Level 1 after4 of 4 · Strike from the Flank, Feint and Vanish'
    );
    expect(screen.getByTestId('reswear-cost')).toHaveTextContent(
      'Cost3 AP from this week · 10 anima · Token of the Vow'
    );
    expect(screen.getByText('Not during a fight.')).toBeInTheDocument();
  });

  it('performs the rite with the picks, the covenant and the paying items', () => {
    mockQueries(OPTIONS);
    renderDialog();

    fireEvent.click(choice('Quick Recovery'));
    fireEvent.click(screen.getByRole('button', { name: 'Perform the rite' }));

    expect(mutate).toHaveBeenCalledWith(
      { ritualId: 40, covenantId: 3, oldPickId: 12, newPickId: 13, componentIds: [88] },
      expect.objectContaining({ onSuccess: expect.any(Function) })
    );
    const { onSuccess } = mutate.mock.calls[0][1] as { onSuccess: (line: string) => void };
    onSuccess('You perform Rite of Re-swearing.');
    expect(onDone).toHaveBeenCalledWith('You perform Rite of Re-swearing.');
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it('shows the refusal the rite gives', () => {
    mockQueries(OPTIONS, new Error('You cannot re-swear a vow pick during a fight.'));
    renderDialog();

    expect(screen.getByRole('alert')).toHaveTextContent(
      'You cannot re-swear a vow pick during a fight.'
    );
  });

  it('says so and cannot perform while no rite is authored', () => {
    mockQueries({
      ...OPTIONS,
      ritual_id: null,
      unavailable_reason: 'No ritual can change a chosen vow pick yet.',
    });
    renderDialog();

    expect(screen.getByRole('status')).toHaveTextContent(
      'No ritual can change a chosen vow pick yet.'
    );
    expect(screen.getByRole('button', { name: 'Perform the rite' })).toBeDisabled();
  });

  it('has a sheet.css rule for every vowpicks class it draws', () => {
    mockQueries(OPTIONS);
    renderDialog();
    const here = path.dirname(fileURLToPath(import.meta.url));
    const css = readFileSync(
      path.resolve(here, '..', '..', '..', 'character_sheets', 'sheet.css'),
      'utf8'
    );
    const drawn = new Set<string>();
    screen
      .getByTestId('reswear-dialog')
      .querySelectorAll('[class]')
      .forEach((node) => {
        node.classList.forEach((name) => {
          if (name.startsWith('vowpicks-')) drawn.add(name);
        });
      });

    expect(drawn.size).toBeGreaterThan(5);
    for (const name of drawn) expect(css).toContain(`.${name}`);
  });
});

/**
 * ResonanceWeights (#5123): the steppers spread the creation points, never past them, and
 * the aura preview says in words what the spread makes.
 */

import { useState } from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ResonanceWeights } from '../../../components/gift/ResonanceWeights';
import type { Resonance, ResonanceWeightPick } from '../../../types';

const resonances: Resonance[] = [
  {
    id: 1,
    name: 'Fury',
    affinity: 2,
    affinity_name: 'Primal',
    description: 'Hot.',
    codex_entry_id: null,
  },
  {
    id: 2,
    name: 'Wonder',
    affinity: 2,
    affinity_name: 'Primal',
    description: '',
    codex_entry_id: null,
  },
  {
    id: 3,
    name: 'Domination',
    affinity: 3,
    affinity_name: 'Abyssal',
    description: '',
    codex_entry_id: null,
  },
];

let saved: ResonanceWeightPick[] = [];

function Harness({ budget = 4, start = [] }: { budget?: number; start?: ResonanceWeightPick[] }) {
  const [weights, setWeights] = useState(start);
  return (
    <ResonanceWeights
      resonances={resonances}
      weights={weights}
      budget={budget}
      onChange={(next) => {
        saved = next;
        setWeights(next);
      }}
    />
  );
}

beforeEach(() => {
  saved = [];
});

describe('ResonanceWeights', () => {
  it('shows the intro and the budget from the server', () => {
    render(<Harness budget={7} />);
    expect(screen.getByText(/Resonance is what powers your magic/)).toBeInTheDocument();
    expect(screen.getByText(/Choose what powers you, and how strongly/)).toBeInTheDocument();
    expect(screen.getByText('0 of 7 placed')).toBeInTheDocument();
    expect(screen.getByText('Hot.')).toBeInTheDocument();
  });

  it('places points with the steppers and saves the whole list', async () => {
    render(<Harness />);
    await userEvent.click(screen.getByRole('button', { name: 'More Fury' }));
    await userEvent.click(screen.getByRole('button', { name: 'More Fury' }));
    await userEvent.click(screen.getByRole('button', { name: 'More Domination' }));
    expect(saved).toEqual([
      { resonance_id: 1, weight: 2 },
      { resonance_id: 3, weight: 1 },
    ]);
    expect(screen.getByText('3 of 4 placed')).toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'Fury: 2 points' })).toBeInTheDocument();
  });

  it('cannot place more than the budget', async () => {
    render(<Harness budget={2} start={[{ resonance_id: 1, weight: 2 }]} />);
    expect(screen.getByText('2 of 2 placed')).toBeInTheDocument();
    for (const name of ['More Fury', 'More Wonder', 'More Domination']) {
      expect(screen.getByRole('button', { name })).toBeDisabled();
    }
    await userEvent.click(screen.getByRole('button', { name: 'Less Fury' }));
    expect(screen.getByRole('button', { name: 'More Wonder' })).toBeEnabled();
  });

  it('drops a resonance when its last point comes off', async () => {
    render(
      <Harness
        start={[
          { resonance_id: 1, weight: 1 },
          { resonance_id: 3, weight: 2 },
        ]}
      />
    );
    await userEvent.click(screen.getByRole('button', { name: 'Less Fury' }));
    expect(saved).toEqual([{ resonance_id: 3, weight: 2 }]);
    expect(screen.queryByRole('button', { name: 'Less Fury' })).not.toBeInTheDocument();
  });

  it('says the aura in words as the points move, never in numbers', async () => {
    render(<Harness budget={10} />);
    expect(screen.queryByTestId('aura-halo-sentence')).not.toBeInTheDocument();
    expect(screen.queryByText('Your aura')).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'More Fury' }));
    expect(screen.getByText('Your aura')).toBeInTheDocument();
    expect(screen.getByTestId('aura-halo-sentence')).toHaveTextContent('All of it primal.');
    await userEvent.click(screen.getByRole('button', { name: 'More Domination' }));
    expect(screen.getByTestId('aura-halo-sentence')).toHaveTextContent(
      'Half primal, half abyssal.'
    );
    await userEvent.click(screen.getByRole('button', { name: 'More Fury' }));
    expect(screen.getByTestId('aura-halo-sentence')).toHaveTextContent(
      'Mostly primal, a third abyssal.'
    );
  });
});

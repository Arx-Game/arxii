/**
 * StrengthStep (#5231): a feeling, a side and a balance. Each change writes one whole list that
 * obeys the server's rule, the aura is named for the balance, and a draft saved under the old
 * rule renders without error and shows only what the rule allows.
 */

import { useState } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { StrengthStep } from '../../../components/gift/StrengthStep';
import {
  mainAffinityOf,
  picksFromWeights,
  strengthPicksComplete,
  weightsFromPicks,
} from '../../../resonanceWeights';
import type { Resonance, ResonanceWeightPick } from '../../../types';

function resonance(id: number, name: string, affinity: string, hex: string): Resonance {
  return {
    id,
    name,
    affinity: 1,
    affinity_name: affinity,
    description: `${name} describes itself.`,
    codex_entry_id: null,
    color_hex: hex,
  };
}

const resonances: Resonance[] = [
  resonance(1, 'Arderi', 'Primal', '#E0642A'),
  resonance(2, 'Sereni', 'Primal', '#7FB7D0'),
  resonance(3, 'Bene', 'Celestial', '#F6EFA0'),
  resonance(4, 'Misera', 'Celestial', '#F4D6E2'),
  resonance(5, 'Praedari', 'Abyssal', '#3A1D1D'),
  resonance(6, 'Dominari', 'Abyssal', '#26153A'),
];

let saved: ResonanceWeightPick[] = [];

function Harness({
  budget = 8,
  start = [],
  copy,
}: {
  budget?: number;
  start?: ResonanceWeightPick[];
  copy?: Record<string, string>;
}) {
  const [weights, setWeights] = useState(start);
  return (
    <StrengthStep
      resonances={resonances}
      weights={weights}
      budget={budget}
      copy={copy}
      onChange={(next) => {
        saved = next;
        setWeights(next);
      }}
    />
  );
}

beforeEach(() => {
  saved = [];
  // jsdom has no canvas: the aura draws nothing, the step still renders.
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(null);
});

describe('StrengthStep', () => {
  it('renders every question and the plate from the start, with nothing chosen', () => {
    render(<Harness />);
    expect(screen.getByText('Where your strength comes from')).toBeInTheDocument();
    expect(screen.getByText('Which feeling gives you strength')).toBeInTheDocument();
    expect(
      screen.getByText('Does what you do to other people give you strength')
    ).toBeInTheDocument();
    expect(screen.getByText('Which of these gives you strength')).toBeInTheDocument();
    expect(screen.getByText('Which gives you more strength')).toBeInTheDocument();
    const arderi = screen.getByRole('button', { name: /Arderi/ });
    expect(arderi).toHaveTextContent('Arderi describes itself.');
    for (const name of ['Helping them', 'Hurting them', 'Neither']) {
      expect(screen.getByRole('button', { name, pressed: false })).toBeInTheDocument();
    }
    expect(screen.queryByRole('button', { name: /Bene|Praedari/ })).not.toBeInTheDocument();
    // The plate is there, in grey, naming nothing; the slider waits for both picks.
    expect(document.querySelector('.strength-plate canvas')).not.toBeNull();
    expect(document.querySelector('.strength-named')).toBeNull();
    expect(document.querySelector('.strength-said')).toBeNull();
    expect(screen.getByRole('slider')).toBeDisabled();
    expect(screen.queryByText(/nothing to balance/)).not.toBeInTheDocument();
  });

  it('writes a valid one-pick list when the side and its card are picked before a feeling', async () => {
    render(<Harness />);
    await userEvent.click(screen.getByRole('button', { name: 'Hurting them' }));
    expect(saved).toEqual([{ resonance_id: 5, weight: 8 }]);
    expect(screen.getByRole('button', { name: /Praedari/, pressed: true })).toBeInTheDocument();
    expect(screen.getByRole('slider')).toBeDisabled();
    expect(document.querySelector('.strength-named')).toBeNull();

    await userEvent.click(screen.getByRole('button', { name: /Dominari/ }));
    expect(saved).toEqual([{ resonance_id: 6, weight: 8 }]);

    // The feeling then joins it, the Primal pick first, and the slider wakes.
    await userEvent.click(screen.getByRole('button', { name: /Arderi/ }));
    expect(saved).toEqual([
      { resonance_id: 1, weight: 6 },
      { resonance_id: 6, weight: 2 },
    ]);
    expect(screen.getByRole('slider')).toBeEnabled();
  });

  it('reads its words from the copy keys', () => {
    render(<Harness copy={{ gift_strength_heading: 'Your strength, in the words staff wrote' }} />);
    expect(screen.getByText('Your strength, in the words staff wrote')).toBeInTheDocument();
  });

  it('sends the feeling alone with every point, then the side, then the second pick', async () => {
    render(<Harness />);
    await userEvent.click(screen.getByRole('button', { name: /Arderi/ }));
    expect(saved).toEqual([{ resonance_id: 1, weight: 8 }]);
    expect(screen.getByRole('button', { name: 'Neither', pressed: true })).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Hurting them' }));
    // The feeling gave up a share to the first card of the side, in one write.
    expect(saved).toEqual([
      { resonance_id: 1, weight: 6 },
      { resonance_id: 5, weight: 2 },
    ]);
    expect(screen.getByRole('button', { name: /Praedari/, pressed: true })).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: /Dominari/ }));
    expect(saved).toEqual([
      { resonance_id: 1, weight: 6 },
      { resonance_id: 6, weight: 2 },
    ]);
  });

  it('replaces the second pick in one write when the side changes, keeping the balance', async () => {
    render(
      <Harness
        start={[
          { resonance_id: 1, weight: 5 },
          { resonance_id: 5, weight: 3 },
        ]}
      />
    );
    await userEvent.click(screen.getByRole('button', { name: 'Helping them' }));
    expect(saved).toEqual([
      { resonance_id: 1, weight: 5 },
      { resonance_id: 3, weight: 3 },
    ]);
    expect(screen.queryByRole('button', { name: /Praedari/ })).not.toBeInTheDocument();
  });

  it('divides the points with the slider, the feeling first', () => {
    render(
      <Harness
        start={[
          { resonance_id: 1, weight: 6 },
          { resonance_id: 5, weight: 2 },
        ]}
      />
    );
    const slider = screen.getByRole('slider');
    expect(slider).toHaveAttribute('min', '1');
    expect(slider).toHaveAttribute('max', '7');
    fireEvent.change(slider, { target: { value: '6' } });
    expect(saved).toEqual([
      { resonance_id: 1, weight: 2 },
      { resonance_id: 5, weight: 6 },
    ]);
    expect(screen.getByText('Arderi 2 · Praedari 6')).toBeInTheDocument();
    expect(screen.getByText('Abyssal, with a Primal side')).toBeInTheDocument();
    expect(
      screen.getByText('Most of your strength comes from what you do to others.')
    ).toBeInTheDocument();
  });

  it('names the aura Primal on an even split', () => {
    render(
      <Harness
        start={[
          { resonance_id: 1, weight: 4 },
          { resonance_id: 3, weight: 4 },
        ]}
      />
    );
    expect(screen.getByText('Primal, with a Celestial side')).toBeInTheDocument();
    expect(screen.getByText('Most of your strength comes from what you feel.')).toBeInTheDocument();
  });

  it('sends the feeling alone for Neither, hides the second cards and turns the slider off', async () => {
    render(
      <Harness
        start={[
          { resonance_id: 1, weight: 5 },
          { resonance_id: 3, weight: 3 },
        ]}
      />
    );
    await userEvent.click(screen.getByRole('button', { name: 'Neither' }));
    expect(saved).toEqual([{ resonance_id: 1, weight: 8 }]);
    expect(screen.queryByRole('button', { name: /Bene/ })).not.toBeInTheDocument();
    expect(screen.getByRole('slider')).toBeDisabled();
    expect(
      screen.getByText(
        'With no second pick there is nothing to balance. All 8 points go to the feeling.'
      )
    ).toBeInTheDocument();
    expect(screen.getByText('Primal')).toBeInTheDocument();
    expect(screen.getByText('All your strength comes from what you feel.')).toBeInTheDocument();
    expect(screen.getByText('Arderi 8')).toBeInTheDocument();
  });

  it('shows nothing chosen for a three-pick draft saved under the old rule', () => {
    render(
      <Harness
        start={[
          { resonance_id: 2, weight: 4 },
          { resonance_id: 5, weight: 2 },
          { resonance_id: 3, weight: 2 },
        ]}
      />
    );
    expect(document.querySelectorAll('[aria-pressed="true"]')).toHaveLength(0);
    expect(screen.getByRole('slider')).toBeDisabled();
    expect(document.querySelector('.strength-named')).toBeNull();
  });

  it('shows nothing chosen for a partial spread that leaves points unplaced', () => {
    render(<Harness budget={10} start={[{ resonance_id: 1, weight: 4 }]} />);
    expect(document.querySelectorAll('[aria-pressed="true"]')).toHaveLength(0);
    expect(document.querySelector('.strength-named')).toBeNull();
  });

  it('shows nothing chosen for two Primal picks, or a Celestial and an Abyssal pick', () => {
    const { unmount } = render(
      <Harness
        start={[
          { resonance_id: 1, weight: 4 },
          { resonance_id: 2, weight: 4 },
        ]}
      />
    );
    expect(document.querySelectorAll('[aria-pressed="true"]')).toHaveLength(0);
    unmount();
    render(
      <Harness
        start={[
          { resonance_id: 3, weight: 4 },
          { resonance_id: 5, weight: 4 },
        ]}
      />
    );
    expect(document.querySelectorAll('[aria-pressed="true"]')).toHaveLength(0);
  });

  it('still shows a valid feeling-only list with every point as chosen', () => {
    render(<Harness start={[{ resonance_id: 1, weight: 8 }]} />);
    expect(screen.getByRole('button', { name: /Arderi/, pressed: true })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Neither', pressed: true })).toBeInTheDocument();
  });

  it('shows a valid second-pick-only list as chosen, with no aura name', () => {
    render(<Harness start={[{ resonance_id: 5, weight: 8 }]} />);
    expect(screen.getByRole('button', { name: 'Hurting them', pressed: true })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Praedari/, pressed: true })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Arderi/, pressed: false })).toBeInTheDocument();
    expect(document.querySelector('.strength-named')).toBeNull();
  });
});

describe('the picks helpers', () => {
  it('reads the picks, writes them back, and judges a list against the rule', () => {
    const list = [
      { resonance_id: 1, weight: 5 },
      { resonance_id: 3, weight: 3 },
    ];
    const picks = picksFromWeights(list, resonances, 8);
    expect(picks).toEqual({ primal: 1, lean: 'give', outward: 3, primalPoints: 5 });
    expect(weightsFromPicks(picks, 8)).toEqual(list);
    expect(mainAffinityOf(picks, 8)).toBe('Primal');
    expect(mainAffinityOf({ ...picks, primalPoints: 3 }, 8)).toBe('Celestial');
    expect(strengthPicksComplete(list, resonances, 8)).toBe(true);
    expect(strengthPicksComplete([{ resonance_id: 1, weight: 8 }], resonances, 8)).toBe(true);
    expect(picksFromWeights([{ resonance_id: 5, weight: 8 }], resonances, 8)).toMatchObject({
      primal: null,
      lean: 'take',
      outward: 5,
    });
    expect(picksFromWeights([{ resonance_id: 1, weight: 3 }], resonances, 8)).toEqual({
      primal: null,
      lean: null,
      outward: null,
      primalPoints: 8,
    });
  });

  it('refuses every list the old rule allowed and the new one does not', () => {
    const complete = (weights: ResonanceWeightPick[]) =>
      strengthPicksComplete(weights, resonances, 8);
    expect(complete([])).toBe(false);
    expect(complete([{ resonance_id: 5, weight: 8 }])).toBe(false);
    expect(
      complete([
        { resonance_id: 1, weight: 4 },
        { resonance_id: 2, weight: 4 },
      ])
    ).toBe(false);
    expect(
      complete([
        { resonance_id: 1, weight: 4 },
        { resonance_id: 3, weight: 2 },
        { resonance_id: 5, weight: 2 },
      ])
    ).toBe(false);
    expect(complete([{ resonance_id: 1, weight: 5 }])).toBe(false);
  });
});

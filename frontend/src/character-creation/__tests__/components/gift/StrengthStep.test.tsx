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
import type { Affinity, Resonance, ResonanceWeightPick } from '../../../types';

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
  affinities,
}: {
  budget?: number;
  start?: ResonanceWeightPick[];
  copy?: Record<string, string>;
  affinities?: Affinity[];
}) {
  const [weights, setWeights] = useState(start);
  return (
    <StrengthStep
      resonances={resonances}
      affinities={affinities}
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
  it('shows each affinity description with its cards, and nothing for a blank one', async () => {
    // Regression for #5293: staff write each affinity's description and no screen showed it.
    const affinities: Affinity[] = [
      { id: 1, name: 'Primal', description: 'What you feel.' },
      { id: 2, name: 'Celestial', description: 'What you give to others.' },
      { id: 3, name: 'Abyssal', description: '' },
    ];
    render(<Harness affinities={affinities} />);
    expect(
      screen.getAllByTestId('strength-affinity-description').map((p) => p.textContent)
    ).toEqual(['What you feel.']);

    await userEvent.click(screen.getByRole('button', { name: 'Helping them' }));
    expect(
      screen.getAllByTestId('strength-affinity-description').map((p) => p.textContent)
    ).toEqual(['What you feel.', 'What you give to others.']);

    await userEvent.click(screen.getByRole('button', { name: 'Hurting them' }));
    expect(
      screen.getAllByTestId('strength-affinity-description').map((p) => p.textContent)
    ).toEqual(['What you feel.']);
  });

  it('renders every question and the plate from the start, with nothing chosen', () => {
    render(<Harness />);
    expect(screen.getByText('Where your strength comes from')).toBeInTheDocument();
    expect(screen.getByText('Which feeling gives you strength')).toBeInTheDocument();
    expect(
      screen.getByText('Does what you do to other people give you strength')
    ).toBeInTheDocument();
    expect(screen.getByText('Which gives you more strength')).toBeInTheDocument();
    // The question about the second pick waits for a side to be chosen.
    expect(screen.queryByText('Which of these gives you strength')).not.toBeInTheDocument();
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

  it('presses no card for her when a side is chosen, and saves nothing until she picks', async () => {
    render(<Harness />);
    await userEvent.click(screen.getByRole('button', { name: 'Hurting them' }));
    expect(saved).toEqual([]);
    expect(screen.getByRole('button', { name: 'Hurting them', pressed: true })).toBeInTheDocument();
    // The side's eight cards are there, none pressed; the slider and the plate stay as they were.
    for (const name of [/Praedari/, /Dominari/]) {
      expect(screen.getByRole('button', { name, pressed: false })).toBeInTheDocument();
    }
    expect(screen.getByRole('slider')).toBeDisabled();
    expect(document.querySelector('.strength-named')).toBeNull();

    await userEvent.click(screen.getByRole('button', { name: /Dominari/ }));
    expect(saved).toEqual([{ resonance_id: 6, weight: 8 }]);
    expect(screen.getByRole('slider')).toBeDisabled();

    // The feeling then joins it, the Primal pick first, and the slider wakes.
    await userEvent.click(screen.getByRole('button', { name: /Arderi/ }));
    expect(saved).toEqual([
      { resonance_id: 1, weight: 6 },
      { resonance_id: 6, weight: 2 },
    ]);
    expect(screen.getByRole('slider')).toBeEnabled();
  });

  const SKIPPED =
    'With no second pick there is nothing to balance. All 8 points go to the feeling.';

  it('leaves all three answers unpressed and shows no skipped line for a feeling on an empty draft', async () => {
    render(<Harness />);
    await userEvent.click(screen.getByRole('button', { name: /Arderi/ }));
    for (const name of ['Helping them', 'Hurting them', 'Neither']) {
      expect(screen.getByRole('button', { name, pressed: false })).toBeInTheDocument();
    }
    expect(screen.queryByText(SKIPPED)).not.toBeInTheDocument();
    // The plate shows the feeling alone, with its caption; the slider stays off.
    expect(screen.getByText('Primal')).toBeInTheDocument();
    expect(screen.getByRole('slider')).toBeDisabled();
    // A second feeling picked later changes no answer either.
    await userEvent.click(screen.getByRole('button', { name: /Sereni/ }));
    expect(screen.getByRole('button', { name: 'Neither', pressed: false })).toBeInTheDocument();
    expect(screen.queryByText(SKIPPED)).not.toBeInTheDocument();
  });

  it('shows no skipped line while a side is pressed with no card picked', async () => {
    render(<Harness start={[{ resonance_id: 1, weight: 8 }]} />);
    // Arrived as a feeling alone: Neither is pressed and the line shows.
    expect(screen.getByRole('button', { name: 'Neither', pressed: true })).toBeInTheDocument();
    expect(screen.getByText(SKIPPED)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Hurting them' }));
    expect(screen.getByRole('button', { name: 'Hurting them', pressed: true })).toBeInTheDocument();
    expect(screen.queryByText(SKIPPED)).not.toBeInTheDocument();
    expect(screen.getByRole('slider')).toBeDisabled();
    expect(screen.getByText('Primal')).toBeInTheDocument();
    // Pressing Neither again brings the line back and saves the feeling at the full budget.
    await userEvent.click(screen.getByRole('button', { name: 'Neither' }));
    expect(screen.getByText(SKIPPED)).toBeInTheDocument();
    expect(saved).toEqual([{ resonance_id: 1, weight: 8 }]);
  });

  it('shows the skipped line when Neither is pressed with a feeling picked', async () => {
    render(<Harness />);
    await userEvent.click(screen.getByRole('button', { name: 'Neither' }));
    // No feeling yet: the line waits for one.
    expect(screen.queryByText(SKIPPED)).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /Arderi/ }));
    expect(screen.getByRole('button', { name: 'Neither', pressed: true })).toBeInTheDocument();
    expect(screen.getByText(SKIPPED)).toBeInTheDocument();
  });

  it('reads its words from the copy keys', () => {
    render(<Harness copy={{ gift_strength_heading: 'Your strength, in the words staff wrote' }} />);
    expect(screen.getByText('Your strength, in the words staff wrote')).toBeInTheDocument();
  });

  it('sends the feeling alone with every point, keeps it when a side is chosen, then the pick', async () => {
    render(<Harness />);
    await userEvent.click(screen.getByRole('button', { name: /Arderi/ }));
    expect(saved).toEqual([{ resonance_id: 1, weight: 8 }]);
    // Picking a feeling answers nothing about others.
    expect(screen.getByRole('button', { name: 'Neither', pressed: false })).toBeInTheDocument();

    saved = [];
    await userEvent.click(screen.getByRole('button', { name: 'Hurting them' }));
    // Choosing the side writes nothing and picks nothing: the slider stays off, the plate stays.
    expect(saved).toEqual([]);
    expect(screen.getByRole('button', { name: 'Neither', pressed: false })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Praedari/, pressed: false })).toBeInTheDocument();
    expect(screen.getByRole('slider')).toBeDisabled();
    expect(screen.getByText('Primal')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: /Praedari/ }));
    // The feeling gave up a share to her pick, in one write.
    expect(saved).toEqual([
      { resonance_id: 1, weight: 6 },
      { resonance_id: 5, weight: 2 },
    ]);
    expect(screen.getByRole('button', { name: /Praedari/, pressed: true })).toBeInTheDocument();
    expect(screen.getByRole('slider')).toBeEnabled();

    await userEvent.click(screen.getByRole('button', { name: /Dominari/ }));
    expect(saved).toEqual([
      { resonance_id: 1, weight: 6 },
      { resonance_id: 6, weight: 2 },
    ]);
  });

  it('clears a second pick from the other side when the side changes, and picks nothing new', async () => {
    render(
      <Harness
        start={[
          { resonance_id: 1, weight: 5 },
          { resonance_id: 5, weight: 3 },
        ]}
      />
    );
    await userEvent.click(screen.getByRole('button', { name: 'Helping them' }));
    expect(saved).toEqual([{ resonance_id: 1, weight: 8 }]);
    expect(screen.queryByRole('button', { name: /Praedari/ })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Bene/, pressed: false })).toBeInTheDocument();
    expect(screen.getByRole('slider')).toBeDisabled();

    await userEvent.click(screen.getByRole('button', { name: /Bene/ }));
    expect(saved).toEqual([
      { resonance_id: 1, weight: 6 },
      { resonance_id: 3, weight: 2 },
    ]);
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
    expect(strengthPicksComplete([], resonances, 8)).toBe(false);
    expect(strengthPicksComplete([{ resonance_id: 5, weight: 8 }], resonances, 8)).toBe(false);
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
});

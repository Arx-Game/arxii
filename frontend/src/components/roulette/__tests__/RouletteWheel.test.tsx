import { render, screen } from '@testing-library/react';
import { RouletteWheel } from '../RouletteWheel';
import type { ConsequenceDisplay } from '../types';

function consequence(
  label: string,
  weight: number,
  tier_name = 'Success',
  is_selected = false
): ConsequenceDisplay {
  return { label, weight, tier_name, is_selected };
}

function getSlices(): HTMLElement[] {
  return screen.getAllByTestId('roulette-slice');
}

describe('RouletteWheel', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('gives each slice a sweep proportional to its weight', () => {
    const consequences = [
      consequence('Critical Failure', 2),
      consequence('Failure', 43),
      consequence('Partial Success', 33),
      consequence('Success', 22, 'Success', true),
    ];

    render(
      <RouletteWheel
        consequences={consequences}
        onAnimationComplete={vi.fn()}
        skipRequested={false}
      />
    );

    const slices = getSlices();
    expect(slices).toHaveLength(4);

    const expectedSweeps = [7.2, 154.8, 118.8, 79.2];
    slices.forEach((slice, index) => {
      const sweep = Number(slice.dataset.sliceSweep);
      expect(sweep).toBeCloseTo(expectedSweeps[index], 1);
    });

    // Sweeps are laid out clockwise from 12 o'clock, back to back with no gaps.
    let expectedStart = 0;
    slices.forEach((slice) => {
      expect(Number(slice.dataset.sliceStart)).toBeCloseTo(expectedStart, 5);
      expectedStart += Number(slice.dataset.sliceSweep);
    });
  });

  it('lands inside the selected slice, not always at its centre', () => {
    vi.spyOn(Math, 'random').mockReturnValue(0.5);

    const consequences = [consequence('Failure', 40), consequence('Success', 60, 'Success', true)];

    render(
      <RouletteWheel
        consequences={consequences}
        onAnimationComplete={vi.fn()}
        skipRequested={false}
      />
    );

    const slices = getSlices();
    const selected = slices.find((slice) => slice.dataset.sliceSelected === 'true');
    expect(selected).toBeDefined();

    const start = Number(selected!.dataset.sliceStart);
    const sweep = Number(selected!.dataset.sliceSweep);
    const disc = screen.getByTestId('roulette-disc');
    const landingAngle = Number(disc.dataset.landingAngle);

    expect(landingAngle).toBeGreaterThan(start);
    expect(landingAngle).toBeLessThan(start + sweep);
    // With Math.random mocked to 0.5, the landing fraction is the midpoint
    // of the allowed [0.2, 0.8] range, i.e. exactly the slice's centre.
    expect(landingAngle).toBeCloseTo(start + sweep * 0.5, 5);
  });

  it('renders two slices for a two-face chart', () => {
    const consequences = [
      consequence('Success', 50, 'Success', true),
      consequence('Critical Success', 50),
    ];

    render(
      <RouletteWheel
        consequences={consequences}
        onAnimationComplete={vi.fn()}
        skipRequested={false}
      />
    );

    expect(getSlices()).toHaveLength(2);
  });

  it('renders a single face as one full-circle slice', () => {
    const consequences = [consequence('Success', 100, 'Success', true)];

    render(
      <RouletteWheel
        consequences={consequences}
        onAnimationComplete={vi.fn()}
        skipRequested={false}
      />
    );

    const slices = getSlices();
    expect(slices).toHaveLength(1);
    expect(Number(slices[0].dataset.sliceSweep)).toBeCloseTo(360, 1);
  });

  it('labels only slices at or above 12% of the total', () => {
    const consequences = [
      consequence('Critical Failure', 2), // 2% - no label
      consequence('Failure', 43), // 43% - label
      consequence('Partial Success', 33), // 33% - label
      consequence('Success', 22, 'Success', true), // 22% - label
    ];

    render(
      <RouletteWheel
        consequences={consequences}
        onAnimationComplete={vi.fn()}
        skipRequested={false}
      />
    );

    const labels = screen.getAllByTestId('wheel-slice-label');
    expect(labels).toHaveLength(3);
    const labelText = labels.map((label) => label.textContent);
    expect(labelText).toEqual(expect.arrayContaining(['43%', '33%', '22%']));
    expect(labelText).not.toEqual(expect.arrayContaining(['2%']));
  });

  it('lists odds in reverse payload order with the correct percentages', () => {
    const consequences = [
      consequence('Critical Failure', 2),
      consequence('Failure', 43),
      consequence('Partial Success', 33),
      consequence('Success', 22, 'Success', true),
    ];

    render(
      <RouletteWheel
        consequences={consequences}
        onAnimationComplete={vi.fn()}
        skipRequested={false}
      />
    );

    const rows = screen.getAllByTestId('odds-row');
    expect(rows.map((row) => row.textContent)).toEqual([
      expect.stringContaining('Success'),
      expect.stringContaining('Partial Success'),
      expect.stringContaining('Failure'),
      expect.stringContaining('Critical Failure'),
    ]);

    const percentages = rows.map(
      (row) => row.querySelector('[data-testid="odds-percentage"]')?.textContent
    );
    expect(percentages).toEqual(['22%', '33%', '43%', '2%']);
  });

  it('calls onAnimationComplete exactly once when skip is requested', () => {
    const onAnimationComplete = vi.fn();
    const consequences = [consequence('Failure', 40), consequence('Success', 60, 'Success', true)];

    const { rerender } = render(
      <RouletteWheel
        consequences={consequences}
        onAnimationComplete={onAnimationComplete}
        skipRequested={false}
      />
    );

    expect(onAnimationComplete).not.toHaveBeenCalled();

    rerender(
      <RouletteWheel
        consequences={consequences}
        onAnimationComplete={onAnimationComplete}
        skipRequested={true}
      />
    );

    expect(onAnimationComplete).toHaveBeenCalledTimes(1);

    // Re-rendering again with skip still requested must not call it again.
    rerender(
      <RouletteWheel
        consequences={consequences}
        onAnimationComplete={onAnimationComplete}
        skipRequested={true}
      />
    );

    expect(onAnimationComplete).toHaveBeenCalledTimes(1);
  });
});

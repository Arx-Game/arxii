/**
 * Pips - generic filled/total row (#3568). No SceneClockPips equivalent
 * lives on this branch, so this is the shared primitive both the mission
 * beat cards and any future track UI reuse.
 */
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { Pips } from '../ui/pips';

describe('Pips', () => {
  it('renders one pip per total, marking the first `filled` as filled', () => {
    render(<Pips filled={2} total={3} label="Successes" testId="pips-test" />);
    expect(screen.getAllByTestId('pips-test-filled')).toHaveLength(2);
    expect(screen.getAllByTestId('pips-test-empty')).toHaveLength(1);
  });

  it('renders the N/total count text', () => {
    render(<Pips filled={1} total={3} label="Successes" testId="pips-test" />);
    expect(screen.getByTestId('pips-test')).toHaveTextContent('1/3');
  });

  it('sets an accessible label with the counts', () => {
    render(<Pips filled={1} total={3} label="Successes" testId="pips-test" />);
    expect(screen.getByRole('img', { name: 'Successes 1 of 3' })).toBeInTheDocument();
  });

  it('renders zero filled pips when filled is 0', () => {
    render(<Pips filled={0} total={2} label="Failures" testId="pips-test" tone="failure" />);
    expect(screen.queryByTestId('pips-test-filled')).not.toBeInTheDocument();
    expect(screen.getAllByTestId('pips-test-empty')).toHaveLength(2);
  });
});

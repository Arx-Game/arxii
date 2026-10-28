import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { DigDeep } from './DigDeep';
import { digDeepChipLabel, digDeepCostLabel } from '../diggingDeep';

const paid = {
  free_dig_deeps: 0,
  fatigue_category: 'mental',
  fatigue_cost: 3,
  given_by: null,
  dug_deep_this_round: false,
};

describe('digDeepCostLabel', () => {
  it('names the fatigue pool and amount', () => {
    expect(digDeepCostLabel(paid)).toBe('Costs mental fatigue 3');
  });

  it('says free while a free dig deep is held', () => {
    expect(digDeepCostLabel({ ...paid, free_dig_deeps: 1 })).toBe('Free');
  });
});

describe('digDeepChipLabel', () => {
  it('credits the ally whose encouragement gave the dig deep', () => {
    expect(digDeepChipLabel({ ...paid, free_dig_deeps: 1, given_by: 'Bram' })).toBe(
      "1 free dig deep from Bram's encouragement"
    );
    expect(digDeepChipLabel({ ...paid, free_dig_deeps: 2, given_by: 'Bram' })).toBe(
      "2 free dig deeps from Bram's encouragement"
    );
  });

  it('falls back to the bare count with no giver', () => {
    expect(digDeepChipLabel({ ...paid, free_dig_deeps: 1 })).toBe('1 free dig deep');
  });
});

describe('DigDeep', () => {
  it('dispatches the combat_dig_deep registry action', async () => {
    const dispatchAction = vi
      .fn()
      .mockResolvedValue({ backend: 'registry', deferred: false, success: true, message: '' });
    render(<DigDeep offer={paid} isLocked={false} dispatchAction={dispatchAction} />);

    await userEvent.click(screen.getByTestId('dig-deep-button'));

    expect(dispatchAction).toHaveBeenCalledWith({
      ref: { backend: 'registry', registry_key: 'combat_dig_deep' },
      kwargs: {},
    });
    expect(screen.queryByTestId('dig-deep-chip')).toBeNull();
  });

  it('shows the free dig deep chip and a free cost', () => {
    render(
      <DigDeep offer={{ ...paid, free_dig_deeps: 2 }} isLocked={false} dispatchAction={vi.fn()} />
    );
    expect(screen.getByTestId('dig-deep-chip')).toHaveTextContent('2 free dig deeps');
    expect(screen.getByTestId('dig-deep-cost')).toHaveTextContent('Free');
  });

  it('is disabled once she has dug deep this round', () => {
    render(
      <DigDeep
        offer={{ ...paid, dug_deep_this_round: true }}
        isLocked={false}
        dispatchAction={vi.fn()}
      />
    );
    expect(screen.getByTestId('dig-deep-button')).toBeDisabled();
  });

  it('is disabled when locked', () => {
    render(<DigDeep offer={paid} isLocked dispatchAction={vi.fn()} />);
    expect(screen.getByTestId('dig-deep-button')).toBeDisabled();
  });
});

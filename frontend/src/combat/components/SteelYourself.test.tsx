import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { SteelYourself } from './SteelYourself';
import { steelCostLabel } from '../steeling';

const paid = { free_steels: 0, fatigue_category: 'mental', fatigue_cost: 3 };

describe('steelCostLabel', () => {
  it('names the fatigue pool and amount', () => {
    expect(steelCostLabel(paid)).toBe('Costs mental fatigue 3');
  });

  it('says free while a free steel is held', () => {
    expect(steelCostLabel({ ...paid, free_steels: 1 })).toBe('Free');
  });
});

describe('SteelYourself', () => {
  it('dispatches the combat_steel registry action', async () => {
    const dispatchAction = vi
      .fn()
      .mockResolvedValue({ backend: 'registry', deferred: false, success: true, message: '' });
    render(<SteelYourself offer={paid} isLocked={false} dispatchAction={dispatchAction} />);

    await userEvent.click(screen.getByTestId('steel-button'));

    expect(dispatchAction).toHaveBeenCalledWith({
      ref: { backend: 'registry', registry_key: 'combat_steel' },
      kwargs: {},
    });
    expect(screen.queryByTestId('steel-chip')).toBeNull();
  });

  it('shows the free-steel chip and a free cost', () => {
    render(
      <SteelYourself
        offer={{ ...paid, free_steels: 2 }}
        isLocked={false}
        dispatchAction={vi.fn()}
      />
    );
    expect(screen.getByTestId('steel-chip')).toHaveTextContent('2 free steels');
    expect(screen.getByTestId('steel-cost')).toHaveTextContent('Free');
  });

  it('is disabled when locked', () => {
    render(<SteelYourself offer={paid} isLocked dispatchAction={vi.fn()} />);
    expect(screen.getByTestId('steel-button')).toBeDisabled();
  });
});

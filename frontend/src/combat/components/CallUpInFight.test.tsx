import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { CallUpInFight } from './CallUpInFight';

const shadow = {
  gift_id: 7,
  label: 'shadow',
  effective_cost: 3,
  resonance_cost: 1,
  already_present: false,
  can_call_up: true,
  cost_line: '3 anima, 1 Umbral resonance',
  balance_line: 'Anima: 30 · after: 27 · Umbral resonance after: 9',
};

describe('CallUpInFight', () => {
  it('says what calling up costs and dispatches the registry action', async () => {
    const dispatchAction = vi
      .fn()
      .mockResolvedValue({ backend: 'registry', deferred: false, success: true, message: '' });
    render(
      <CallUpInFight
        offer={{ offers: [shadow], called_up_this_round: false }}
        isLocked={false}
        dispatchAction={dispatchAction}
      />
    );

    expect(screen.getByTestId('call-up-cost')).toHaveTextContent('3 anima, 1 Umbral resonance');
    await userEvent.click(screen.getByTestId('call-up-button'));

    expect(dispatchAction).toHaveBeenCalledWith({
      ref: { backend: 'registry', registry_key: 'call_up_substance' },
      kwargs: { gift_id: 7, confirm_soulfray_risk: false },
    });
  });

  it('is spent once this round, and asks once past the soulfray warning', async () => {
    const { rerender } = render(
      <CallUpInFight
        offer={{ offers: [shadow], called_up_this_round: true }}
        isLocked={false}
        dispatchAction={vi.fn()}
      />
    );
    expect(screen.getByTestId('call-up-button')).toBeDisabled();

    const dispatchAction = vi
      .fn()
      .mockResolvedValue({ backend: 'registry', deferred: false, success: true, message: '' })
      .mockResolvedValueOnce({
        backend: 'registry',
        deferred: false,
        success: false,
        message: 'Calling up shadow will cost 3 anima and may worsen your condition.',
        data: { needs_soulfray_confirm: true },
      });
    rerender(
      <CallUpInFight
        offer={{ offers: [shadow], called_up_this_round: false }}
        isLocked={false}
        dispatchAction={dispatchAction}
      />
    );
    await userEvent.click(screen.getByTestId('call-up-button'));
    await userEvent.click(await screen.findByText('Call it up anyway'));

    expect(dispatchAction).toHaveBeenLastCalledWith({
      ref: { backend: 'registry', registry_key: 'call_up_substance' },
      kwargs: { gift_id: 7, confirm_soulfray_risk: true },
    });
  });
});

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { StrikeControl, type StrikeWeaponOption } from './StrikeControl';

const rapier: StrikeWeaponOption = {
  item_instance_id: 11,
  name: 'Rapier',
  gear_kind: 'One-Handed Melee',
  strike_skill: 'Melee Combat',
};
const bareHands: StrikeWeaponOption = {
  item_instance_id: null,
  name: 'bare hands',
  gear_kind: 'Unarmed',
  strike_skill: 'Unarmed Combat',
};

describe('StrikeControl', () => {
  const baseProps = {
    weapons: [rapier, bareHands],
    targetOpponentId: 5,
    declaredTargetName: null,
    error: null,
    disabled: false,
    pending: false,
  };

  it('names each weapon with its gear kind in sentence case and its strike skill', () => {
    render(<StrikeControl {...baseProps} onStrike={vi.fn()} />);
    expect(screen.getByTestId('strike-weapon-11')).toHaveTextContent(
      'Rapierone-handed melee · Melee Combat'
    );
    expect(screen.getByTestId('strike-weapon-bare')).toHaveTextContent(
      'bare handsunarmed · Unarmed Combat'
    );
    expect(screen.getByTestId('strike-weapon-11')).toHaveAttribute('aria-checked', 'true');
  });

  it('strikes the shared target with the chosen weapon', async () => {
    const onStrike = vi.fn();
    const user = userEvent.setup();
    render(<StrikeControl {...baseProps} onStrike={onStrike} />);

    await user.click(screen.getByTestId('strike-confirm-btn'));
    expect(onStrike).toHaveBeenLastCalledWith(5, 11);

    await user.click(screen.getByTestId('strike-weapon-bare'));
    await user.click(screen.getByTestId('strike-confirm-btn'));
    expect(onStrike).toHaveBeenLastCalledWith(5, null);
  });

  it('waits for a target before it can strike', () => {
    render(<StrikeControl {...baseProps} targetOpponentId={null} onStrike={vi.fn()} />);
    expect(screen.getByTestId('strike-confirm-btn')).toBeDisabled();
  });

  it('re-seeds the weapon when the list arrives late or the chosen one goes away', () => {
    const { rerender } = render(<StrikeControl {...baseProps} weapons={[]} onStrike={vi.fn()} />);
    rerender(<StrikeControl {...baseProps} weapons={[rapier, bareHands]} onStrike={vi.fn()} />);
    expect(screen.getByTestId('strike-weapon-11')).toHaveAttribute('aria-checked', 'true');

    rerender(<StrikeControl {...baseProps} weapons={[bareHands]} onStrike={vi.fn()} />);
    expect(screen.getByTestId('strike-weapon-bare')).toHaveAttribute('aria-checked', 'true');
  });

  it('shows the declared strike and the server refusal', () => {
    render(
      <StrikeControl
        {...baseProps}
        declaredTargetName="Bandit"
        error="Cannot strike: Bandit is out of reach of your Rapier."
        onStrike={vi.fn()}
      />
    );
    expect(screen.getByTestId('strike-declared-badge')).toHaveTextContent('Striking Bandit');
    expect(screen.getByRole('alert')).toHaveTextContent('out of reach');
  });

  it("starts on the weapon this round's Strike was declared with", () => {
    render(<StrikeControl {...baseProps} declaredItemInstanceId={null} onStrike={vi.fn()} />);
    expect(screen.getByTestId('strike-weapon-bare')).toHaveAttribute('aria-checked', 'true');
  });
});

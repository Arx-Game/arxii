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
    opponents: [{ id: 5, name: 'Bandit' }],
    declaredTargetName: null,
    error: null,
    disabled: false,
    inactive: false,
    pending: false,
  };

  it('renders nothing with no opponent to strike', () => {
    const { container } = render(
      <StrikeControl {...baseProps} opponents={[]} onStrike={vi.fn()} />
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('names each weapon with its gear kind and strike skill', () => {
    render(<StrikeControl {...baseProps} onStrike={vi.fn()} />);
    expect(screen.getByTestId('strike-weapon-11')).toHaveTextContent(
      'RapierOne-Handed Melee · Melee Combat'
    );
    expect(screen.getByTestId('strike-weapon-bare')).toHaveTextContent(
      'bare handsUnarmed · Unarmed Combat'
    );
    expect(screen.getByTestId('strike-weapon-11')).toHaveAttribute('aria-checked', 'true');
  });

  it('strikes the chosen opponent with the chosen weapon', async () => {
    const onStrike = vi.fn();
    const user = userEvent.setup();
    render(<StrikeControl {...baseProps} onStrike={onStrike} />);

    const confirm = screen.getByTestId('strike-confirm-btn');
    expect(confirm).toBeDisabled();
    await user.click(screen.getByTestId('strike-opponent-select'));
    await user.click(await screen.findByRole('option', { name: 'Bandit' }));
    await user.click(confirm);
    expect(onStrike).toHaveBeenLastCalledWith(5, 11);

    await user.click(screen.getByTestId('strike-weapon-bare'));
    await user.click(confirm);
    expect(onStrike).toHaveBeenLastCalledWith(5, null);
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
});

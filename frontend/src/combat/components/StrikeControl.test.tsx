import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import type { PlayerAction } from '@/scenes/actionTypes';
import { StrikeControl, type StrikeWeaponOption } from './StrikeControl';

const rapier: StrikeWeaponOption = {
  item_instance_id: 11,
  name: 'Rapier',
  gear_kind: 'One-Handed Melee',
  strike_skill: 'Melee Combat',
  thrown: false,
  damage_share: null,
};
const dagger: StrikeWeaponOption = {
  item_instance_id: 12,
  name: 'Parrying dagger',
  gear_kind: 'One-Handed Melee',
  strike_skill: 'Melee Combat',
  thrown: false,
  damage_share: null,
};
const daggerThrown: StrikeWeaponOption = {
  item_instance_id: 12,
  name: 'Parrying dagger',
  gear_kind: 'Thrown',
  strike_skill: 'Thrown Combat',
  thrown: true,
  damage_share: 75,
};
const bareHands: StrikeWeaponOption = {
  item_instance_id: null,
  name: 'bare hands',
  gear_kind: 'Unarmed',
  strike_skill: 'Unarmed Combat',
  thrown: false,
  damage_share: null,
};

function enchantment(overrides: Partial<PlayerAction> = {}): PlayerAction {
  return {
    backend: 'combat',
    display_name: 'Wreathe the blade',
    description: '',
    difficulty: null,
    prerequisite_met: true,
    prerequisite_reasons: [],
    check_type: { id: 1, name: 'Magic' },
    action_template: null,
    ref: { backend: 'combat', technique_id: 40 },
    target_spec: null,
    enhancements: [],
    strain: null,
    soulfray_warning: null,
    cast_preview: { intensity: 5, control: 5, effective_anima_cost: 4 },
    enchants_strike: true,
    enchant_damage_types: ['fire'],
    ...overrides,
  } as PlayerAction;
}

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
    expect(onStrike).toHaveBeenLastCalledWith(5, {
      itemInstanceId: 11,
      thrown: false,
      techniqueId: null,
      confirmSoulfrayRisk: false,
    });

    await user.click(screen.getByTestId('strike-weapon-bare'));
    await user.click(screen.getByTestId('strike-confirm-btn'));
    expect(onStrike).toHaveBeenLastCalledWith(5, {
      itemInstanceId: null,
      thrown: false,
      techniqueId: null,
      confirmSoulfrayRisk: false,
    });
  });

  it('offers a throwable dagger twice and throws it at its share', async () => {
    const onStrike = vi.fn();
    const user = userEvent.setup();
    render(
      <StrikeControl
        {...baseProps}
        weapons={[dagger, daggerThrown, bareHands]}
        onStrike={onStrike}
      />
    );
    expect(screen.getByTestId('strike-weapon-12-thrown')).toHaveTextContent(
      'Parrying dagger, thrownThrown Combat · 75% damage'
    );

    await user.click(screen.getByTestId('strike-weapon-12-thrown'));
    await user.click(screen.getByTestId('strike-confirm-btn'));
    expect(onStrike).toHaveBeenLastCalledWith(5, {
      itemInstanceId: 12,
      thrown: true,
      techniqueId: null,
      confirmSoulfrayRisk: false,
    });
  });

  it('casts a weapon technique into the Strike, its cost on the chip', async () => {
    const onStrike = vi.fn();
    const user = userEvent.setup();
    render(<StrikeControl {...baseProps} enchantments={[enchantment()]} onStrike={onStrike} />);
    expect(screen.getByTestId('strike-enchant-none')).toHaveAttribute('aria-checked', 'true');
    expect(screen.getByTestId('strike-enchant-40')).toHaveTextContent(
      'Wreathe the bladefire · 4 anima'
    );

    await user.click(screen.getByTestId('strike-enchant-40'));
    await user.click(screen.getByTestId('strike-confirm-btn'));
    expect(onStrike).toHaveBeenLastCalledWith(5, {
      itemInstanceId: 11,
      thrown: false,
      techniqueId: 40,
      confirmSoulfrayRisk: false,
    });
  });

  it('waits for the soulfray accept box before an enchantment that carries a warning', async () => {
    const onStrike = vi.fn();
    const user = userEvent.setup();
    const risky = enchantment({
      soulfray_warning: {
        stage_name: 'Fraying',
        stage_description: 'Your soul thins.',
        has_death_risk: false,
      },
    });
    render(<StrikeControl {...baseProps} enchantments={[risky]} onStrike={onStrike} />);

    await user.click(screen.getByTestId('strike-enchant-40'));
    expect(screen.getByTestId('soulfray-accept-gate')).toBeInTheDocument();
    expect(screen.getByTestId('strike-confirm-btn')).toBeDisabled();

    await user.click(screen.getByTestId('soulfray-accept-checkbox'));
    await user.click(screen.getByTestId('strike-confirm-btn'));
    expect(onStrike).toHaveBeenLastCalledWith(5, {
      itemInstanceId: 11,
      thrown: false,
      techniqueId: 40,
      confirmSoulfrayRisk: true,
    });
  });

  it('names the picked target and how far it stands', () => {
    render(
      <StrikeControl
        {...baseProps}
        targetSummary="Bandit archer · 2 positions away"
        onStrike={vi.fn()}
      />
    );
    expect(screen.getByTestId('strike-target')).toHaveTextContent(
      'Target: Bandit archer · 2 positions away'
    );
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

  it("starts on the weapon, use and enchantment this round's Strike was declared with", () => {
    render(
      <StrikeControl
        {...baseProps}
        weapons={[dagger, daggerThrown, bareHands]}
        enchantments={[enchantment()]}
        declaredItemInstanceId={12}
        declaredThrown
        declaredTechniqueId={40}
        onStrike={vi.fn()}
      />
    );
    expect(screen.getByTestId('strike-weapon-12-thrown')).toHaveAttribute('aria-checked', 'true');
    expect(screen.getByTestId('strike-enchant-40')).toHaveAttribute('aria-checked', 'true');
  });
});

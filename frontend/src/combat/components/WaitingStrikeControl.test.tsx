import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { WaitingStrikeControl } from './WaitingStrikeControl';
import { waitingStrikeTechniques } from '../roundActionHelpers';
import type { PlayerAction } from '@/scenes/actionTypes';

function technique(id: number, name: string, reach: string | null): PlayerAction {
  return {
    backend: 'combat',
    display_name: name,
    description: '',
    difficulty: null,
    prerequisite_met: true,
    prerequisite_reasons: [],
    check_type: { id: 1, name: 'Standard' },
    action_template: null,
    ref: {
      backend: 'combat',
      challenge_instance_id: null,
      approach_id: null,
      technique_id: id,
      registry_key: null,
      position_id: null,
    },
    target_spec: null,
    enhancements: [],
    strain: null,
    reach,
  };
}

const lunge = technique(7, 'Lunge', 'adjacent');

describe('waitingStrikeTechniques', () => {
  it('keeps only combat techniques that reach the same or the next position', () => {
    const kept = waitingStrikeTechniques([
      lunge,
      technique(8, 'Grapple', 'same'),
      technique(9, 'Sling Stone', 'any'),
      technique(10, 'Old Habit', null),
    ]);
    expect(kept.map((a) => a.display_name)).toEqual(['Lunge', 'Grapple']);
  });
});

describe('WaitingStrikeControl', () => {
  const baseProps = {
    techniques: [lunge],
    declaredTechniqueName: null,
    error: null,
    disabled: false,
    inactive: false,
    pending: false,
  };

  it('renders nothing when no technique can be held', () => {
    const { container } = render(
      <WaitingStrikeControl {...baseProps} techniques={[]} onDeclare={vi.fn()} />
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('declares the chosen technique', async () => {
    const onDeclare = vi.fn();
    const user = userEvent.setup();
    render(<WaitingStrikeControl {...baseProps} onDeclare={onDeclare} />);

    const confirm = screen.getByTestId('waiting-strike-confirm-btn');
    expect(confirm).toBeDisabled();
    await user.click(screen.getByTestId('waiting-strike-technique-select'));
    await user.click(await screen.findByRole('option', { name: 'Lunge' }));
    await user.click(confirm);

    expect(onDeclare).toHaveBeenCalledWith(7, false);
  });

  it('shows the strike held this round and the server refusal', () => {
    render(
      <WaitingStrikeControl
        {...baseProps}
        declaredTechniqueName="Lunge"
        error="You do not know that technique."
        onDeclare={vi.fn()}
      />
    );
    expect(screen.getByTestId('waiting-strike-declared-badge')).toHaveTextContent(
      'Waiting for an opening: Lunge'
    );
    expect(screen.getByRole('alert')).toHaveTextContent('You do not know that technique.');
  });
});

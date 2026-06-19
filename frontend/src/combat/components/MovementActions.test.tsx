import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { MovementActions } from './MovementActions';
import type { PlayerAction } from '@/scenes/actionTypes';

function makeMoveAction(positionId: number, displayName: string): PlayerAction {
  return {
    backend: 'registry',
    display_name: displayName,
    description: '',
    difficulty: null,
    prerequisite_met: true,
    prerequisite_reasons: [],
    check_type: { id: 1, name: 'Standard' },
    action_template: null,
    ref: {
      backend: 'registry',
      challenge_instance_id: null,
      approach_id: null,
      technique_id: null,
      registry_key: 'move_to_position',
      position_id: positionId,
    },
    target_spec: null,
    enhancements: [],
    strain: null,
  };
}

describe('MovementActions', () => {
  it('renders one button per action', () => {
    const actions = [makeMoveAction(1, 'Move to North Wall'), makeMoveAction(2, 'Move to Center')];
    const dispatchAction = vi.fn(() => Promise.resolve());

    render(<MovementActions actions={actions} isLocked={false} dispatchAction={dispatchAction} />);

    expect(screen.getByTestId('move-btn-1')).toBeInTheDocument();
    expect(screen.getByTestId('move-btn-2')).toBeInTheDocument();
    expect(screen.getByText('Move to North Wall')).toBeInTheDocument();
    expect(screen.getByText('Move to Center')).toBeInTheDocument();
  });

  it('click dispatches with the action ref and empty kwargs', async () => {
    const action = makeMoveAction(5, 'Move to Balcony');
    const dispatchAction = vi.fn(() => Promise.resolve());
    const user = userEvent.setup();

    render(<MovementActions actions={[action]} isLocked={false} dispatchAction={dispatchAction} />);

    await user.click(screen.getByTestId('move-btn-5'));

    expect(dispatchAction).toHaveBeenCalledWith({ ref: action.ref, kwargs: {} });
  });

  it('buttons are disabled when isLocked is true', () => {
    const actions = [makeMoveAction(3, 'Move to Gate')];
    const dispatchAction = vi.fn(() => Promise.resolve());

    render(<MovementActions actions={actions} isLocked={true} dispatchAction={dispatchAction} />);

    expect(screen.getByTestId('move-btn-3')).toBeDisabled();
  });

  it('renders nothing when actions array is empty', () => {
    const dispatchAction = vi.fn(() => Promise.resolve());
    const { container } = render(
      <MovementActions actions={[]} isLocked={false} dispatchAction={dispatchAction} />
    );
    expect(container.firstChild).toBeNull();
  });
});

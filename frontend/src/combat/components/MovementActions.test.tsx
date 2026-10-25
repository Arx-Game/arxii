import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { MovementActions } from './MovementActions';
import type { PlayerAction } from '@/scenes/actionTypes';
import type { DispatchResult } from '@/combat/types';

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

import { toast } from 'sonner';

/** Successful dispatch resolution — the full wire shape the tightened prop type requires. */
function okDispatch(): Promise<DispatchResult> {
  return Promise.resolve({ backend: 'registry', deferred: false, success: true });
}

function makeMoveAction(
  positionId: number | null,
  displayName: string,
  registryKey = 'move_to_position'
): PlayerAction {
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
      registry_key: registryKey,
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
    const dispatchAction = vi.fn(okDispatch);

    render(<MovementActions actions={actions} isLocked={false} dispatchAction={dispatchAction} />);

    expect(screen.getByTestId('move-btn-move_to_position-1')).toBeInTheDocument();
    expect(screen.getByTestId('move-btn-move_to_position-2')).toBeInTheDocument();
    expect(screen.getByText('Move to North Wall')).toBeInTheDocument();
    expect(screen.getByText('Move to Center')).toBeInTheDocument();
  });

  it('click dispatches with the action ref and empty kwargs', async () => {
    const action = makeMoveAction(5, 'Move to Balcony');
    const dispatchAction = vi.fn(okDispatch);
    const user = userEvent.setup();

    render(<MovementActions actions={[action]} isLocked={false} dispatchAction={dispatchAction} />);

    await user.click(screen.getByTestId('move-btn-move_to_position-5'));

    expect(dispatchAction).toHaveBeenCalledWith({ ref: action.ref, kwargs: {} });
  });

  it('buttons are disabled when isLocked is true', () => {
    const actions = [makeMoveAction(3, 'Move to Gate')];
    const dispatchAction = vi.fn(okDispatch);

    render(<MovementActions actions={actions} isLocked={true} dispatchAction={dispatchAction} />);

    expect(screen.getByTestId('move-btn-move_to_position-3')).toBeDisabled();
  });

  it('renders nothing when actions array is empty', () => {
    const dispatchAction = vi.fn(okDispatch);
    const { container } = render(
      <MovementActions actions={[]} isLocked={false} dispatchAction={dispatchAction} />
    );
    expect(container.firstChild).toBeNull();
  });

  // ---------------------------------------------------------------------------
  // Dispatch contract (#2423) — the endpoint resolves HTTP 200 + success:false
  // for a business-rule rejection, so a resolved promise is not itself proof
  // of success.
  // ---------------------------------------------------------------------------

  it('shows a toast and skips onDispatched on success:false', async () => {
    vi.clearAllMocks();
    const action = makeMoveAction(5, 'Move to Balcony');
    const dispatchAction = vi.fn(() =>
      Promise.resolve({ backend: 'registry', deferred: false, success: false, message: 'Blocked.' })
    );
    const onDispatched = vi.fn();
    const user = userEvent.setup();

    render(
      <MovementActions
        actions={[action]}
        isLocked={false}
        dispatchAction={dispatchAction}
        onDispatched={onDispatched}
      />
    );

    await user.click(screen.getByTestId('move-btn-move_to_position-5'));

    expect(toast.error).toHaveBeenCalledWith('Blocked.');
    expect(onDispatched).not.toHaveBeenCalled();
  });

  it('calls onDispatched when the dispatch resolves success:true', async () => {
    vi.clearAllMocks();
    const action = makeMoveAction(5, 'Move to Balcony');
    const dispatchAction = vi.fn(() =>
      Promise.resolve({ backend: 'registry', deferred: false, success: true })
    );
    const onDispatched = vi.fn();
    const user = userEvent.setup();

    render(
      <MovementActions
        actions={[action]}
        isLocked={false}
        dispatchAction={dispatchAction}
        onDispatched={onDispatched}
      />
    );

    await user.click(screen.getByTestId('move-btn-move_to_position-5'));

    expect(onDispatched).toHaveBeenCalled();
    expect(toast.error).not.toHaveBeenCalled();
  });

  it('disables a refused move and shows why under the label', () => {
    const refused: PlayerAction = {
      ...makeMoveAction(7, 'Move to Gate'),
      prerequisite_met: false,
      prerequisite_reasons: ['You have no movement left this round.'],
    };

    render(
      <MovementActions actions={[refused]} isLocked={false} dispatchAction={vi.fn(okDispatch)} />
    );

    expect(screen.getByTestId('move-btn-move_to_position-7')).toBeDisabled();
    expect(screen.getByText('You have no movement left this round.')).toBeInTheDocument();
    expect(screen.queryByTestId('movement-hops-line')).not.toBeInTheDocument();
  });

  it('shows the hops left once under the Move heading', () => {
    const actions = [
      { ...makeMoveAction(1, 'Move to North Wall'), description: '2 hops left this round.' },
      { ...makeMoveAction(2, 'Move to Center'), description: '2 hops left this round.' },
    ];

    render(
      <MovementActions actions={actions} isLocked={false} dispatchAction={vi.fn(okDispatch)} />
    );

    expect(screen.getAllByText('2 hops left this round.')).toHaveLength(1);
    expect(screen.getByTestId('move-btn-move_to_position-1')).toBeEnabled();
  });

  // ---------------------------------------------------------------------------
  // Movement by capability and held ground (#4663)
  // ---------------------------------------------------------------------------

  it('lists a move and a pass roll into the same held place as two buttons', () => {
    const actions = [
      {
        ...makeMoveAction(4, 'Move to Gatehouse'),
        description: "Held by Bandit: you'd stop there.",
      },
      {
        ...makeMoveAction(4, 'Get past Bandit into Gatehouse', 'pass_held_ground'),
        description: 'Slip past',
      },
    ];

    render(
      <MovementActions actions={actions} isLocked={false} dispatchAction={vi.fn(okDispatch)} />
    );

    expect(screen.getByTestId('move-btn-move_to_position-4')).toBeInTheDocument();
    expect(screen.getByTestId('move-btn-pass_held_ground-4')).toBeInTheDocument();
    expect(screen.getByText("Held by Bandit: you'd stop there.")).toBeInTheDocument();
    expect(screen.getByText('Slip past')).toBeInTheDocument();
  });

  it('offers take flight and finds the hops line on any move entry', () => {
    const actions = [
      {
        ...makeMoveAction(4, 'Move to Gatehouse'),
        description: "Held by Bandit: you'd stop there.",
      },
      {
        ...makeMoveAction(null, 'Take flight', 'take_flight'),
        description: '1 hop left this round.',
      },
    ];

    render(
      <MovementActions actions={actions} isLocked={false} dispatchAction={vi.fn(okDispatch)} />
    );

    expect(screen.getByTestId('movement-hops-line')).toHaveTextContent('1 hop left this round.');
    expect(screen.getByTestId('move-btn-take_flight-here')).toBeEnabled();
    expect(screen.getAllByText('1 hop left this round.')).toHaveLength(1);
  });

  it('toasts the result message after a pass roll', async () => {
    vi.clearAllMocks();
    const action = makeMoveAction(4, 'Get past Bandit into Gatehouse', 'pass_held_ground');
    const dispatchAction = vi.fn(() =>
      Promise.resolve({
        backend: 'registry',
        deferred: false,
        success: true,
        message: 'You get past Bandit into Gatehouse.',
      })
    );
    const user = userEvent.setup();

    render(<MovementActions actions={[action]} isLocked={false} dispatchAction={dispatchAction} />);
    await user.click(screen.getByTestId('move-btn-pass_held_ground-4'));

    expect(toast.success).toHaveBeenCalledWith('You get past Bandit into Gatehouse.');
  });
});

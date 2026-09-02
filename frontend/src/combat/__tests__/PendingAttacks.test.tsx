import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { PendingAttacks } from '../components/PendingAttacks';
import type { PendingAttack } from '../types';

function row(overrides: Partial<PendingAttack> = {}): PendingAttack {
  return {
    id: 1,
    opponent_id: 10,
    opponent_name: 'Ogre',
    target_participant_id: 5,
    target_name: 'Kira',
    declared_round: 1,
    resolves_round: 3,
    rounds_until_landing: 1,
    downgrades: 1,
    called_out: true,
    damage_scale: 0.75,
    cancelled: false,
    ...overrides,
  };
}

describe('PendingAttacks', () => {
  it('renders nothing when there are no pending attacks', () => {
    const { container } = render(<PendingAttacks attacks={[]} viewerParticipantId={5} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('shows opponent, target, landing round, pips and called-out badge', () => {
    render(<PendingAttacks attacks={[row()]} viewerParticipantId={99} />);
    const item = screen.getByTestId('pending-attack-1');
    expect(item).toHaveTextContent('Ogre');
    expect(item).toHaveTextContent('Kira');
    expect(item).toHaveTextContent(/lands in 1/i);
    expect(within(item).getAllByTestId('downgrade-pip-filled')).toHaveLength(1);
    expect(within(item).getAllByTestId('downgrade-pip-empty')).toHaveLength(2);
    expect(within(item).getByText(/called out/i)).toBeInTheDocument();
  });

  it('says "lands this round" at zero and marks cancelled rows', () => {
    render(
      <PendingAttacks
        attacks={[row({ rounds_until_landing: 0, downgrades: 3, cancelled: true })]}
        viewerParticipantId={99}
      />
    );
    const item = screen.getByTestId('pending-attack-1');
    expect(item).toHaveTextContent(/lands this round/i);
    expect(item).toHaveTextContent(/broken/i);
  });

  it('fires the prefill callbacks', async () => {
    const onGuard = vi.fn();
    const onStrike = vi.fn();
    render(
      <PendingAttacks
        attacks={[row()]}
        viewerParticipantId={99}
        onGuard={onGuard}
        onStrike={onStrike}
      />
    );
    await userEvent.click(screen.getByTestId('pending-attack-guard-1'));
    await userEvent.click(screen.getByTestId('pending-attack-strike-1'));
    expect(onGuard).toHaveBeenCalledWith(5);
    expect(onStrike).toHaveBeenCalledWith(10);
  });

  it('omits Guard when the viewer is the target, and both buttons for observers', () => {
    const { rerender } = render(
      <PendingAttacks
        attacks={[row()]}
        viewerParticipantId={5}
        onGuard={vi.fn()}
        onStrike={vi.fn()}
      />
    );
    expect(screen.queryByTestId('pending-attack-guard-1')).toBeNull();
    expect(screen.getByTestId('pending-attack-strike-1')).toBeInTheDocument();
    rerender(<PendingAttacks attacks={[row()]} viewerParticipantId={null} />);
    expect(screen.queryByTestId('pending-attack-guard-1')).toBeNull();
    expect(screen.queryByTestId('pending-attack-strike-1')).toBeNull();
  });

  it('omits Guard when the wind-up has no target', () => {
    render(
      <PendingAttacks
        attacks={[row({ target_participant_id: null, target_name: null })]}
        viewerParticipantId={99}
        onGuard={vi.fn()}
        onStrike={vi.fn()}
      />
    );
    expect(screen.getByTestId('pending-attack-1')).toHaveTextContent(/no one/i);
    expect(screen.queryByTestId('pending-attack-guard-1')).toBeNull();
  });
});

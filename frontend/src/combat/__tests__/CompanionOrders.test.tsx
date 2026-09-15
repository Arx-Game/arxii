import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { EncounterDetail } from '../types';
import { CompanionOrders } from '../sections/CompanionOrders';

const { mutateAsync } = vi.hoisted(() => ({ mutateAsync: vi.fn() }));

vi.mock('@/companions/queries', () => ({
  useMyCompanions: () => ({
    data: [
      {
        id: 7,
        name: 'Ash',
        archetype: { name: 'Direwolf' },
        objectdb_id: 11,
      },
    ],
  }),
}));

vi.mock('../queries', () => ({
  useRegistryDispatch: () => ({ mutateAsync, isPending: false }),
}));

const encounter = {
  id: 3,
  status: 'declaring',
  is_participant: true,
  round_number: 2,
  opponents: [
    { id: 22, objectdb_id: 11, name: 'Goblin', status: 'active', allegiance: 'enemy' },
    { id: 23, objectdb_id: 12, name: 'Ogre', status: 'active', allegiance: 'enemy' },
  ],
  participants: [{ id: 4, character_name: 'Mira', status: 'active' }],
  companion_orders: [
    {
      companion_id: 7,
      companion_name: 'Ash',
      order_kind: 'attack_target',
      target_opponent_id: 22,
      defending_participant_id: null,
    },
  ],
} as unknown as EncounterDetail;

describe('CompanionOrders', () => {
  beforeEach(() => {
    mutateAsync.mockReset();
    mutateAsync.mockResolvedValue({ success: true, message: 'Order accepted.' });
  });

  it('highlights the saved order and offers reset for a draft change', async () => {
    const user = userEvent.setup();
    render(<CompanionOrders encounter={encounter} encounterId={3} characterId={9} />);

    expect(screen.getByTestId('companion-attack_target-7')).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByTestId('companion-hold-7')).toHaveAttribute('aria-pressed', 'false');

    await user.click(screen.getByTestId('companion-defend_ally-7'));
    expect(screen.getByTestId('companion-reset-7')).toBeInTheDocument();

    await user.click(screen.getByTestId('companion-reset-7'));
    expect(screen.getByTestId('companion-attack_target-7')).toHaveAttribute('aria-pressed', 'true');
    expect(mutateAsync).not.toHaveBeenCalled();
  });

  it('dispatches Hold immediately through the registry seam', async () => {
    const user = userEvent.setup();
    render(<CompanionOrders encounter={encounter} encounterId={3} characterId={9} />);

    await user.click(screen.getByTestId('companion-hold-7'));
    expect(mutateAsync).toHaveBeenCalledWith({
      registryKey: 'order_companion',
      kwargs: { companion_id: 7, order_kind: 'hold' },
    });
  });
});

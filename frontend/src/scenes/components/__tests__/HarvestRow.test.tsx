import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { HarvestOffer } from '@/hooks/types';
import { HarvestRow } from '../HarvestRow';

const mutateAsync = vi.fn();
vi.mock('@/combat/queries', () => ({
  useDispatchPlayerAction: () => ({ mutateAsync, isPending: false }),
}));

const elemental: HarvestOffer = {
  substance_id: 3,
  substance_name: 'fire',
  source: 'creature',
  opponent_id: 41,
  opponent_name: 'Fire elemental',
  step_name: 'Rich',
  check_name: 'Harvesting',
  ap_cost: 2,
  character_id: 9,
};

describe('HarvestRow', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders nothing without offers', () => {
    const { container } = render(<HarvestRow offers={[]} characterId={9} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("dispatches harvest_primum with the offer's substance and opponent", async () => {
    const onAnswer = vi.fn();
    mutateAsync.mockResolvedValue({
      backend: 'registry',
      deferred: false,
      success: true,
      message: 'Success. You draw out 1 Fire Primum (Common).',
      data: { remaining_line: 'Nothing more can be drawn from Fire elemental.' },
    });
    render(<HarvestRow offers={[elemental]} characterId={9} onAnswer={onAnswer} />);

    expect(screen.getByText('You sense fire Primum in its remains.')).toBeInTheDocument();
    expect(screen.getByText('Check: Harvesting')).toBeInTheDocument();
    expect(screen.getByText('Costs 2 AP')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Harvest' }));

    expect(mutateAsync).toHaveBeenCalledWith({
      ref: { backend: 'registry', registry_key: 'harvest_primum' },
      kwargs: { substance: 3, opponent_id: 41 },
    });
    expect(onAnswer).toHaveBeenCalledWith({
      success: true,
      message: 'Success. You draw out 1 Fire Primum (Common).',
      remainingLine: 'Nothing more can be drawn from Fire elemental.',
    });
  });

  it('names the bonus her thread on the matching Gift adds to the check', () => {
    render(
      <HarvestRow
        offers={[{ ...elemental, thread_bonus: 2, thread_gift_name: 'Pyromancy' }]}
        characterId={9}
      />
    );
    expect(
      screen.getByText('Check: Harvesting · +2 from your thread on Pyromancy')
    ).toBeInTheDocument();
  });

  it('keeps the answer on screen once nothing is offered', () => {
    render(
      <HarvestRow
        offers={[]}
        characterId={9}
        answer={{ success: true, message: 'You draw out 1.', remainingLine: '' }}
      />
    );
    expect(screen.getByText('You draw out 1.')).toBeInTheDocument();
  });
});

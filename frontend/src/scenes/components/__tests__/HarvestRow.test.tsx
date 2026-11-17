import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { HarvestOffer } from '@/hooks/types';
import { HarvestRow } from '../HarvestRow';

const mutateAsync = vi.fn();
vi.mock('@/combat/queries', () => ({
  useDispatchPlayerAction: () => ({ mutateAsync, isPending: false }),
}));

const toastSuccess = vi.fn();
const toastError = vi.fn();
vi.mock('sonner', () => ({
  toast: {
    success: (...args: unknown[]) => toastSuccess(...args),
    error: (...args: unknown[]) => toastError(...args),
  },
}));

const lair: HarvestOffer = {
  substance_id: 3,
  substance_name: 'fire',
  source: 'place',
  opponent_id: null,
  opponent_name: '',
  step_name: 'Massive',
};

const elemental: HarvestOffer = {
  substance_id: 3,
  substance_name: 'fire',
  source: 'creature',
  opponent_id: 41,
  opponent_name: 'Fire elemental',
  step_name: 'Rich',
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
    mutateAsync.mockResolvedValue({
      backend: 'registry',
      deferred: false,
      success: true,
      message: 'Success. You draw out 1 Fire Primum.',
    });
    render(<HarvestRow offers={[lair, elemental]} characterId={9} />);

    const buttons = screen.getAllByRole('button', { name: 'Harvest' });
    expect(buttons).toHaveLength(2);
    await userEvent.click(buttons[1]);

    expect(mutateAsync).toHaveBeenCalledWith({
      ref: { backend: 'registry', registry_key: 'harvest_primum' },
      kwargs: { substance: 3, opponent_id: 41 },
    });
    expect(toastSuccess).toHaveBeenCalledWith('Success. You draw out 1 Fire Primum.');
  });
});

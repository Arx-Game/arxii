import { describe, it, expect, vi, beforeEach } from 'vitest';
import { handleRoulettePayload } from '../handleRoulettePayload';
import { enqueueRoulette } from '@/store/rouletteSlice';
import type { AppDispatch } from '@/store/store';
import type { RoulettePayload } from '@/components/roulette/types';

vi.mock('@/store/rouletteSlice', () => ({
  enqueueRoulette: vi.fn((payload) => ({ type: 'roulette/enqueueRoulette', payload })),
}));

describe('handleRoulettePayload', () => {
  let mockDispatch: AppDispatch;

  beforeEach(() => {
    vi.clearAllMocks();
    mockDispatch = vi.fn() as unknown as AppDispatch;
  });

  it('dispatches enqueueRoulette with the payload', () => {
    const payload: RoulettePayload = {
      template_name: 'Sneak Past Guard',
      consequences: [
        { label: 'Guard raises alarm', tier_name: 'Failure', weight: 3, is_selected: false },
        { label: 'You slip past', tier_name: 'Success', weight: 2, is_selected: true },
      ],
    };

    handleRoulettePayload(payload, mockDispatch);

    expect(enqueueRoulette).toHaveBeenCalledWith(payload);
    expect(mockDispatch).toHaveBeenCalledTimes(1);
  });

  it('passes all consequence fields through', () => {
    const payload: RoulettePayload = {
      template_name: 'Test',
      consequences: [{ label: 'Result', tier_name: 'Mixed', weight: 5, is_selected: true }],
    };

    handleRoulettePayload(payload, mockDispatch);

    expect(enqueueRoulette).toHaveBeenCalledWith(
      expect.objectContaining({
        consequences: expect.arrayContaining([
          expect.objectContaining({
            label: 'Result',
            tier_name: 'Mixed',
            weight: 5,
            is_selected: true,
          }),
        ]),
      })
    );
  });
});

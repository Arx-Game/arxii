import { describe, it, expect, vi, beforeEach } from 'vitest';

const { toastMock, invalidateQueriesMock } = vi.hoisted(() => ({
  toastMock: vi.fn(),
  invalidateQueriesMock: vi.fn(),
}));

vi.mock('sonner', () => ({
  toast: Object.assign(toastMock, { error: vi.fn(), success: vi.fn() }),
}));

vi.mock('@/queryClient', () => ({
  queryClient: { invalidateQueries: invalidateQueriesMock },
}));

import { handleKudosReceivedPayload } from '../handleKudosReceivedPayload';
import type { KudosReceivedPayload } from '../types';

describe('handleKudosReceivedPayload', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('fires a quiet toast (never toast.error) with the amount and description', () => {
    const payload: KudosReceivedPayload = {
      amount: 3,
      source_category: 'writeup_commend',
      description: 'A commend for your writeup',
    };

    handleKudosReceivedPayload(payload);

    expect(toastMock).toHaveBeenCalledWith('+3 kudos — A commend for your writeup', {
      description: 'writeup_commend',
    });
  });

  it('invalidates the account-progression query', () => {
    const payload: KudosReceivedPayload = {
      amount: 1,
      source_category: 'pose_chip',
      description: 'Someone applauded your pose',
    };

    handleKudosReceivedPayload(payload);

    expect(invalidateQueriesMock).toHaveBeenCalledWith({ queryKey: ['account-progression'] });
  });

  it('tolerates an undefined payload (malformed frame) without throwing', () => {
    expect(() => handleKudosReceivedPayload(undefined)).not.toThrow();
    expect(toastMock).toHaveBeenCalledWith('+0 kudos — ', { description: '' });
    expect(invalidateQueriesMock).toHaveBeenCalledWith({ queryKey: ['account-progression'] });
  });
});

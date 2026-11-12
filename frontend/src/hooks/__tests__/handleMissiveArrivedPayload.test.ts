import { describe, it, expect, vi, beforeEach } from 'vitest';
import { toast } from 'sonner';
import { handleMissiveArrivedPayload } from '../handleMissiveArrivedPayload';
import { missiveKeys } from '@/missives/queries';
import { queryClient } from '@/queryClient';

vi.mock('sonner', () => ({
  toast: Object.assign(vi.fn(), { error: vi.fn(), success: vi.fn() }),
}));

describe('handleMissiveArrivedPayload', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('names the face written to and the sender, and refetches every missive query', () => {
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries').mockResolvedValue();

    handleMissiveArrivedPayload({
      missive_id: 3,
      recipient_persona_name: 'Hobb',
      sender_display: 'a person wearing an owl mask',
    });

    expect(toast).toHaveBeenCalledWith('A missive for Hobb from a person wearing an owl mask');
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: missiveKeys.all });
    invalidateSpy.mockRestore();
  });
});

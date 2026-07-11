import { describe, it, expect, vi, beforeEach } from 'vitest';
import { toast } from 'sonner';
import { handleMailArrivedPayload } from '../handleMailArrivedPayload';
import { mailKeys } from '@/mail/queries';
import { queryClient } from '@/queryClient';
import type { MailArrivedPayload } from '../types';

vi.mock('sonner', () => ({
  toast: Object.assign(vi.fn(), { error: vi.fn(), success: vi.fn() }),
}));

describe('handleMailArrivedPayload', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows a toast naming the sender and subject', () => {
    const payload: MailArrivedPayload = {
      mail_id: 42,
      sender_display: '1st player of Ariel',
      subject: 'Regarding the border dispute',
    };

    handleMailArrivedPayload(payload);

    expect(toast).toHaveBeenCalledWith(
      'A letter from 1st player of Ariel: Regarding the border dispute'
    );
  });

  it('invalidates the unread mail-count query', () => {
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries').mockResolvedValue();

    const payload: MailArrivedPayload = {
      mail_id: 7,
      sender_display: 'Guardsman Rolf',
      subject: 'Patrol report',
    };

    handleMailArrivedPayload(payload);

    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: mailKeys.unreadCount() });

    invalidateSpy.mockRestore();
  });
});

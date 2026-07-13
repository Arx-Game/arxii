import { toast } from 'sonner';
import type { MailArrivedPayload } from './types';
import { mailKeys } from '@/mail/queries';
import { queryClient } from '@/queryClient';

/**
 * A letter arrived for one of the recipient's tenures (#2160). The payload
 * is a slim ping (no mail body — see `MailArrivedPayload`'s anonymity-boundary
 * note); on receipt we surface a toast and invalidate the unread-count query
 * so the header badge refreshes.
 */
export function handleMailArrivedPayload(payload: MailArrivedPayload) {
  toast(`A letter from ${payload.sender_display}: ${payload.subject}`);
  queryClient.invalidateQueries({ queryKey: mailKeys.unreadCount() });
}

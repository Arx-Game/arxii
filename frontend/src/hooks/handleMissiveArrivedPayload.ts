import { toast } from 'sonner';
import type { MissiveArrivedPayload } from './types';
import { missiveKeys } from '@/missives/queries';
import { queryClient } from '@/queryClient';

/**
 * An IC missive came due for one of this character's faces (#3289). Toast which face
 * it was written to and who sent it, and refetch the missive list and unread count.
 */
export function handleMissiveArrivedPayload(payload: MissiveArrivedPayload) {
  toast(`A missive for ${payload.recipient_persona_name} from ${payload.sender_display}`);
  queryClient.invalidateQueries({ queryKey: missiveKeys.all }).catch(() => {});
}

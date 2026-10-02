import { queryClient } from '@/queryClient';
import { gmPromptKeys } from '@/scenes/gmPromptQueries';

/** A new GM prompt arrived (#4101): refetch every open queue for this GM. */
export function handleGMPromptPayload() {
  queryClient.invalidateQueries({ queryKey: gmPromptKeys.all });
}

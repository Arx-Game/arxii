import type { BattleStatePayload } from '@/battles/types';
import { battleKeys } from '@/battles/queries';
import { queryClient } from '@/queryClient';

/**
 * Battles are location-less (their backing scene has no ``location``), so the
 * existing scene/room broadcast paths never reach participants — ``battle_state``
 * is the dedicated seam (see ``BattleStatePayload`` in
 * ``src/web/webclient/message_types.py``). The payload carries no battle data
 * itself; on receipt we just invalidate so the REST aggregate refetches.
 */
export function handleBattleStatePayload(_payload: BattleStatePayload) {
  void queryClient.invalidateQueries({ queryKey: battleKeys.all });
}

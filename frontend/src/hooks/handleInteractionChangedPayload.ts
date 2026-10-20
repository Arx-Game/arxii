import { queryClient } from '@/queryClient';
import { refreshSceneFeedRow } from '@/scenes/sceneFeedCache';

export interface InteractionChangedPayload {
  interaction_id: number;
  scene_id: number | null;
}

/** A pose's endorsements, tags or reactions changed (#4508): refetch that row for this viewer. */
export function handleInteractionChangedPayload(payload: InteractionChangedPayload) {
  if (payload.scene_id === null) return;
  void refreshSceneFeedRow(queryClient, {
    interactionId: payload.interaction_id,
    sceneId: payload.scene_id,
  });
}

import { PoseUnit } from './PoseUnit';
import type { Interaction } from '../types';
import type { ActionAttachmentInfo } from '../actionTypes';

interface Props {
  sceneId: string;
  filteredInteractions: Interaction[];
  onAddTarget?: (personaName: string) => void;
  onAttachAction?: (action: ActionAttachmentInfo) => void;
}

export function SceneMessages({
  sceneId,
  filteredInteractions,
  onAddTarget,
  onAttachAction,
}: Props) {
  // Collect the set of ACTION interaction IDs that are already embedded inside
  // a POSE via action_links. These are rendered inside their parent PoseUnit
  // and should be skipped at the top-level iteration to avoid duplication.
  const linkedActionIds = new Set<number>();
  for (const msg of filteredInteractions) {
    if (msg.action_links && msg.action_links.length > 0) {
      for (const link of msg.action_links) {
        linkedActionIds.add(link.action_interaction.id);
      }
    }
  }

  return (
    <div>
      {filteredInteractions.map((msg) => {
        // Skip ACTION rows that are embedded in a POSE via action_links.
        if (msg.mode === 'action' && linkedActionIds.has(msg.id)) {
          return null;
        }

        return (
          <PoseUnit
            key={msg.id}
            interaction={msg}
            sceneId={sceneId}
            onAddTarget={onAddTarget}
            onAttachAction={onAttachAction}
          />
        );
      })}
    </div>
  );
}

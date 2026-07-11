/**
 * CombatTacticalMap — spatial rendering of the encounter's Position graph
 * (#2006), mounted as a rail tab in CombatScenePage alongside CombatTurnPanel.
 *
 * Occupants are built from participants'/opponents' current_position (not
 * persona_positions — combat encounters track position on the participant/
 * opponent row directly). Click-to-move reuses the same single-hop
 * move_to_position/take_position PlayerActions the scene view uses.
 */

import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useCombatEncounter, useDispatchPlayerAction } from '../queries';
import { fetchAvailableActions } from '@/scenes/actionQueries';
import { TacticalMap } from '@/areas/components/TacticalMap';
import type { OccupantSummary } from '@/areas/components/PositionMapNode';
import type { PlayerAction } from '@/scenes/actionTypes';

export interface CombatTacticalMapProps {
  encounterId: number;
  characterId: number;
}

export function CombatTacticalMap({ encounterId, characterId }: CombatTacticalMapProps) {
  const { data: encounter } = useCombatEncounter(encounterId);

  const { data: actionsData } = useQuery({
    queryKey: ['available-actions', characterId],
    queryFn: () => fetchAvailableActions(characterId),
    enabled: characterId > 0,
  });

  const availableActions: PlayerAction[] = actionsData?.results ?? [];
  const moveActions = availableActions.filter(
    (a) =>
      a.ref.backend === 'registry' &&
      (a.ref.registry_key === 'move_to_position' || a.ref.registry_key === 'take_position')
  );

  const { mutateAsync: dispatchAction } = useDispatchPlayerAction(characterId);

  const occupantsByPosition = useMemo(() => {
    const map = new Map<number, OccupantSummary[]>();
    for (const participant of encounter?.participants ?? []) {
      if (participant.current_position) {
        const occupants = map.get(participant.current_position.id) ?? [];
        occupants.push({
          name: participant.character_name,
          thumbnailUrl: participant.thumbnail_url,
          thumbnailMediaUrl: participant.thumbnail_media_url,
        });
        map.set(participant.current_position.id, occupants);
      }
    }
    for (const opponent of encounter?.opponents ?? []) {
      if (opponent.current_position) {
        const occupants = map.get(opponent.current_position.id) ?? [];
        occupants.push({
          name: opponent.name,
          thumbnailUrl: opponent.thumbnail_url,
          thumbnailMediaUrl: opponent.thumbnail_media_url,
        });
        map.set(opponent.current_position.id, occupants);
      }
    }
    return map;
  }, [encounter?.participants, encounter?.opponents]);

  if (!encounter) {
    return (
      <div className="p-4 text-sm text-muted-foreground" data-testid="combat-tactical-map-loading">
        Loading map…
      </div>
    );
  }

  const handleDispatchMove = (action: PlayerAction) => {
    dispatchAction({ ref: action.ref, kwargs: {} }).catch(() => {});
  };

  return (
    <div
      className="h-[480px] rounded-lg border border-border bg-card"
      data-testid="combat-tactical-map"
    >
      <TacticalMap
        nodes={encounter.position_nodes ?? []}
        edges={encounter.position_edges ?? []}
        occupantsByPosition={occupantsByPosition}
        moveActions={moveActions}
        onDispatchMove={handleDispatchMove}
      />
    </div>
  );
}

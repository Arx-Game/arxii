/**
 * SceneTacticalMap — spatial rendering of the scene's Position graph (#2006).
 *
 * Replaces RoomPositionsPanel's text list + button list with the tactical
 * map: occupant avatars per node, edges styled by obstacle/gate state,
 * click-to-move via the existing single-hop move_to_position/take_position
 * PlayerActions. Keeps the "Set the Stage" staff/GM affordance.
 *
 * If the scene has no positions, renders nothing.
 */

import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useAppSelector } from '@/store/hooks';
import { useMyRosterEntriesQuery } from '@/roster/queries';
import { useDispatchPlayerAction } from '@/combat/queries';
import { TacticalMap } from '@/areas/components/TacticalMap';
import type { OccupantSummary } from '@/areas/components/PositionMapNode';
import { fetchScene, sceneKeys } from '../queries';
import { fetchAvailableActions } from '../actionQueries';
import type { SceneDetail } from '../types';
import type { PlayerAction } from '../actionTypes';

interface Props {
  sceneId: string;
}

export function SceneTacticalMap({ sceneId }: Props) {
  // ---------------------------------------------------------------------------
  // Resolve active character → characterId for the actions endpoint
  // ---------------------------------------------------------------------------
  const activeCharacterName = useAppSelector((state) => state.game.active);
  const { data: myRosterEntries = [] } = useMyRosterEntriesQuery();
  const characterId = useMemo(
    () => myRosterEntries.find((e) => e.name === activeCharacterName)?.character_id ?? null,
    [myRosterEntries, activeCharacterName]
  );

  // ---------------------------------------------------------------------------
  // Scene detail — position graph nodes/edges, persona_positions
  // ---------------------------------------------------------------------------
  const { data: scene } = useQuery<SceneDetail>({
    queryKey: sceneKeys.detail(sceneId),
    queryFn: () => fetchScene(sceneId),
  });

  // ---------------------------------------------------------------------------
  // Available actions — move_to_position/take_position + set_the_stage
  // ---------------------------------------------------------------------------
  const { data: actionsData } = useQuery({
    queryKey: ['available-actions', characterId],
    queryFn: () => fetchAvailableActions(characterId!),
    enabled: characterId !== null,
  });

  const availableActions: PlayerAction[] = actionsData?.results ?? [];

  const moveActions = availableActions.filter(
    (a) =>
      a.ref.backend === 'registry' &&
      (a.ref.registry_key === 'move_to_position' || a.ref.registry_key === 'take_position')
  );

  const setTheStageAction =
    availableActions.find(
      (a) => a.ref.backend === 'registry' && a.ref.registry_key === 'set_the_stage'
    ) ?? null;

  // ---------------------------------------------------------------------------
  // Dispatch
  // ---------------------------------------------------------------------------
  const { mutateAsync: dispatchAction, isPending } = useDispatchPlayerAction(characterId ?? 0);

  // ---------------------------------------------------------------------------
  // Derived data — build memos before any conditional return (rules of hooks)
  // ---------------------------------------------------------------------------
  const positionNodes = scene?.position_nodes ?? [];
  const positionEdges = scene?.position_edges ?? [];

  const personaNameById = useMemo(() => {
    const personas = scene?.personas ?? [];
    return new Map(personas.map((p) => [p.id, p.name]));
  }, [scene?.personas]);

  const occupantsByPosition = useMemo(() => {
    const personaPositions = scene?.persona_positions ?? [];
    const map = new Map<number, OccupantSummary[]>();
    for (const pp of personaPositions) {
      if (pp.position !== null) {
        const occupants = map.get(pp.position.id) ?? [];
        const name = personaNameById.get(pp.persona_id);
        if (name) occupants.push({ name });
        map.set(pp.position.id, occupants);
      }
    }
    return map;
  }, [scene?.persona_positions, personaNameById]);

  // ---------------------------------------------------------------------------
  // Early exit — no positions defined for this room
  // ---------------------------------------------------------------------------
  if (!scene || positionNodes.length === 0) return null;

  const handleDispatchMove = (action: PlayerAction) => {
    dispatchAction({ ref: action.ref, kwargs: {} }).catch(() => {});
  };

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------
  return (
    <div className="mt-2 space-y-2" data-testid="scene-tactical-map">
      <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        Positions
      </p>
      <div className="h-[320px] rounded-md border border-border">
        <TacticalMap
          nodes={positionNodes}
          edges={positionEdges}
          occupantsByPosition={occupantsByPosition}
          moveActions={moveActions}
          onDispatchMove={handleDispatchMove}
        />
      </div>

      {setTheStageAction && (
        <button
          type="button"
          data-testid="set-the-stage-btn"
          onClick={() => {
            dispatchAction({ ref: setTheStageAction.ref, kwargs: {} }).catch(() => {});
          }}
          disabled={isPending}
          className="w-full rounded border border-blue-500/40 bg-blue-500/5 px-3 py-1.5 text-left text-xs font-medium text-blue-300 transition-colors hover:bg-blue-500/10 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {setTheStageAction.display_name}
        </button>
      )}
    </div>
  );
}

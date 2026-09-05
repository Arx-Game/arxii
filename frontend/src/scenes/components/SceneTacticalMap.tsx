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
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { useAppSelector } from '@/store/hooks';
import { useMyRosterEntriesQuery } from '@/roster/queries';
import { useDispatchPlayerAction } from '@/combat/queries';
import { isDispatchFailure } from '@/combat/types';
import { TacticalMap } from '@/areas/components/TacticalMap';
import { GMPlacementControls } from '@/areas/components/GMPlacementControls';
import type { OccupantSummary } from '@/areas/components/PositionMapNode';
import { fetchScene, sceneKeys } from '../queries';
import { useAvailableActionsQuery } from '../actionQueries';
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
  const { data: actionsData } = useAvailableActionsQuery(characterId, {
    refetchInterval: 10_000,
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

  // GM-place (#3385): a non-empty list is itself the "am I GM" signal —
  // mirrors setTheStageAction above; no separate "can GM" prop.
  const gmPlaceActions = availableActions.filter(
    (a) => a.ref.backend === 'registry' && a.ref.registry_key === 'gm_place_in_position'
  );

  // ---------------------------------------------------------------------------
  // Dispatch
  // ---------------------------------------------------------------------------
  const { mutateAsync: dispatchAction, isPending } = useDispatchPlayerAction(characterId ?? 0);
  const queryClient = useQueryClient();

  // ---------------------------------------------------------------------------
  // Derived data — build memos before any conditional return (rules of hooks)
  // ---------------------------------------------------------------------------
  const positionNodes = scene?.position_nodes ?? [];
  const positionEdges = scene?.position_edges ?? [];

  // Extended to carry the character's ObjectDB pk (CharacterSheet/ObjectDB
  // share a pk, see root CLAUDE.md) alongside the name (#3385) — the GM-place
  // target picker needs it as `target_object_id`.
  const personaById = useMemo(() => {
    const personas = scene?.personas ?? [];
    return new Map(personas.map((p) => [p.id, { name: p.name, characterId: p.character_sheet }]));
  }, [scene?.personas]);

  const occupantsByPosition = useMemo(() => {
    const personaPositions = scene?.persona_positions ?? [];
    const map = new Map<number, OccupantSummary[]>();
    for (const pp of personaPositions) {
      if (pp.position !== null) {
        const occupants = map.get(pp.position.id) ?? [];
        const persona = personaById.get(pp.persona_id);
        if (persona) occupants.push({ name: persona.name });
        map.set(pp.position.id, occupants);
      }
    }
    return map;
  }, [scene?.persona_positions, personaById]);

  // GM-place target picker (#3385): every persona co-located on the graph
  // with a resolvable character ObjectDB pk.
  const placeTargets = useMemo(() => {
    const personaPositions = scene?.persona_positions ?? [];
    const targets: { id: number; name: string }[] = [];
    for (const pp of personaPositions) {
      if (pp.position === null) continue;
      const persona = personaById.get(pp.persona_id);
      if (persona?.characterId != null) {
        targets.push({ id: persona.characterId, name: persona.name });
      }
    }
    return targets;
  }, [scene?.persona_positions, personaById]);

  // ---------------------------------------------------------------------------
  // Early exit — no positions defined for this room
  // ---------------------------------------------------------------------------
  if (!scene || positionNodes.length === 0) return null;

  const handleDispatchMove = (action: PlayerAction) => {
    dispatchAction({ ref: action.ref, kwargs: {} })
      .then((result) => {
        if (isDispatchFailure(result)) {
          toast.error(result.message ?? 'Move rejected.');
          return;
        }
        queryClient.invalidateQueries({ queryKey: sceneKeys.detail(sceneId) }).catch(() => {});
      })
      .catch((err: unknown) => {
        toast.error(err instanceof Error ? err.message : 'Move failed.');
      });
  };

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------
  return (
    <div className="mt-2 space-y-2" data-testid="scene-tactical-map">
      <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        Positions
      </p>
      <GMPlacementControls
        gmPlaceActions={gmPlaceActions}
        targets={placeTargets}
        dispatchAction={dispatchAction}
        onPlaced={() => {
          queryClient.invalidateQueries({ queryKey: sceneKeys.detail(sceneId) }).catch(() => {});
        }}
      >
        {(onGMPlace) => (
          <div className="h-[320px] overflow-hidden rounded-md border border-border">
            <TacticalMap
              nodes={positionNodes}
              edges={positionEdges}
              occupantsByPosition={occupantsByPosition}
              moveActions={moveActions}
              onDispatchMove={handleDispatchMove}
              onGMPlace={onGMPlace}
              artUrl={scene.art_url}
            />
          </div>
        )}
      </GMPlacementControls>

      {setTheStageAction && (
        <button
          type="button"
          data-testid="set-the-stage-btn"
          onClick={() => {
            dispatchAction({ ref: setTheStageAction.ref, kwargs: {} })
              .then((result) => {
                if (isDispatchFailure(result)) {
                  toast.error(result.message ?? 'Could not set the stage.');
                  return;
                }
                queryClient
                  .invalidateQueries({ queryKey: sceneKeys.detail(sceneId) })
                  .catch(() => {});
              })
              .catch((err: unknown) => {
                toast.error(err instanceof Error ? err.message : 'Failed to set the stage.');
              });
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

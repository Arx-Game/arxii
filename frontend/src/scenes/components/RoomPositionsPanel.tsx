/**
 * RoomPositionsPanel — non-combat scene positions display.
 *
 * Renders:
 *   - The room's positions with which personas currently occupy them
 *   - Move-to-position buttons for the current player (reusing MovementActions)
 *   - A "Set the Stage" staff control when that action is available
 *
 * If the scene has no positions, renders nothing.
 */

import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useAppSelector } from '@/store/hooks';
import { useMyRosterEntriesQuery } from '@/roster/queries';
import { useDispatchPlayerAction } from '@/combat/queries';
import { MovementActions } from '@/combat/components/MovementActions';
import { fetchScene, sceneKeys } from '../queries';
import { fetchAvailableActions } from '../actionQueries';
import type { SceneDetail } from '../types';
import type { PlayerAction } from '../actionTypes';

interface Props {
  sceneId: string;
}

export function RoomPositionsPanel({ sceneId }: Props) {
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
  // Scene detail — positions, adjacency, persona_positions
  // ---------------------------------------------------------------------------
  const { data: scene } = useQuery<SceneDetail>({
    queryKey: sceneKeys.detail(sceneId),
    queryFn: () => fetchScene(sceneId),
  });

  // ---------------------------------------------------------------------------
  // Available actions — move_to_position + set_the_stage
  // ---------------------------------------------------------------------------
  const { data: actionsData } = useQuery({
    queryKey: ['available-actions', characterId],
    queryFn: () => fetchAvailableActions(characterId!),
    enabled: characterId !== null,
  });

  const availableActions: PlayerAction[] = actionsData?.results ?? [];

  const moveActions = availableActions.filter(
    (a) => a.ref.backend === 'registry' && a.ref.registry_key === 'move_to_position'
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
  const scenePositions = scene?.positions ?? [];

  const personaNameById = useMemo(() => {
    const personas = scene?.personas ?? [];
    return new Map(personas.map((p) => [p.id, p.name]));
  }, [scene?.personas]);

  const occupantsByPosition = useMemo(() => {
    const personaPositions = scene?.persona_positions ?? [];
    const map = new Map<number, string[]>();
    for (const pp of personaPositions) {
      if (pp.position !== null) {
        const names = map.get(pp.position.id) ?? [];
        const name = personaNameById.get(pp.persona_id);
        if (name) names.push(name);
        map.set(pp.position.id, names);
      }
    }
    return map;
  }, [scene?.persona_positions, personaNameById]);

  // ---------------------------------------------------------------------------
  // Early exit — no positions defined for this room
  // ---------------------------------------------------------------------------
  if (!scene || scenePositions.length === 0) return null;

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------
  return (
    <div className="mt-2 space-y-2" data-testid="room-positions-panel">
      <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        Positions
      </p>

      <div className="space-y-1">
        {scenePositions.map((pos) => {
          const occupants = occupantsByPosition.get(pos.id) ?? [];
          return (
            <div
              key={pos.id}
              className="flex items-center justify-between rounded bg-muted/30 px-2 py-1 text-xs"
            >
              <span className="font-medium">{pos.name}</span>
              {occupants.length > 0 && (
                <span className="ml-2 text-muted-foreground">{occupants.join(', ')}</span>
              )}
            </div>
          );
        })}
      </div>

      {moveActions.length > 0 && (
        <MovementActions
          actions={moveActions}
          isLocked={isPending}
          dispatchAction={dispatchAction}
        />
      )}

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

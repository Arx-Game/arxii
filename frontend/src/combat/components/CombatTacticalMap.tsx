/**
 * CombatTacticalMap — spatial rendering of the encounter's Position graph
 * (#2006), mounted as a rail tab in CombatRail alongside CombatTurnPanel
 * (CombatRail renders in-scene on /scenes/:id — #2197).
 *
 * Occupants are built from participants'/opponents' current_position (not
 * persona_positions — combat encounters track position on the participant/
 * opponent row directly). Click-to-move reuses the same single-hop
 * move_to_position/take_position PlayerActions the scene view uses.
 */

import { useMemo, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { combatKeys, useCombatEncounter, useDispatchPlayerAction } from '../queries';
import { isDispatchFailure } from '../types';
import { useAvailableActionsQuery } from '@/scenes/actionQueries';
import { TacticalMap } from '@/areas/components/TacticalMap';
import type { OccupantSummary } from '@/areas/components/PositionMapNode';
import type { PlayerAction } from '@/scenes/actionTypes';
import type { PositionTargetShape } from '@/actions/types';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

export interface CombatTacticalMapProps {
  encounterId: number;
  characterId: number;
  /**
   * Cast-time position-targeting shape for the currently selected focused
   * technique (#2206), lifted to CombatRail so this map tab can
   * highlight pickable nodes and consume clicks while a position-shaped
   * technique is selected in the sibling "Your Turn" tab. Defaults to 'none'
   * (today's move-only behavior) when the caller omits it.
   */
  positionShape?: PositionTargetShape;
  /**
   * Called when the player clicks a map node while `positionShape !== 'none'`.
   * Only forwarded to TacticalMap when picking is active — see the
   * presence-gated `onPickPosition` handoff below.
   */
  onPickPosition?: (positionId: number) => boolean;
}

export function CombatTacticalMap({
  encounterId,
  characterId,
  positionShape = 'none',
  onPickPosition,
}: CombatTacticalMapProps) {
  const { data: encounter } = useCombatEncounter(encounterId);

  const { data: actionsData } = useAvailableActionsQuery(characterId, {
    refetchInterval: 10_000,
  });

  const availableActions: PlayerAction[] = actionsData?.results ?? [];
  const moveActions = availableActions.filter(
    (a) =>
      a.ref.backend === 'registry' &&
      (a.ref.registry_key === 'move_to_position' || a.ref.registry_key === 'take_position')
  );
  // GM-place (#3385): a non-empty list is itself the "am I GM" signal — the
  // adapter (_gm_place_in_position_actions) only ever emits these when the
  // caller already passes the server-side GM gate. Mirrors the
  // SceneTacticalMap.tsx setTheStageAction pattern — no separate "can GM" prop.
  const gmPlaceActions = availableActions.filter(
    (a) => a.ref.backend === 'registry' && a.ref.registry_key === 'gm_place_in_position'
  );

  const { mutateAsync: dispatchAction } = useDispatchPlayerAction(characterId);
  const queryClient = useQueryClient();

  const [isPlacing, setIsPlacing] = useState(false);
  const [placeTargetId, setPlaceTargetId] = useState<number | null>(null);

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
    dispatchAction({ ref: action.ref, kwargs: {} })
      .then((result) => {
        if (isDispatchFailure(result)) {
          toast.error(result.message ?? 'Move rejected.');
          return;
        }
        queryClient
          .invalidateQueries({ queryKey: combatKeys.encounter(encounterId) })
          .catch(() => {});
      })
      .catch((err: unknown) => {
        toast.error(err instanceof Error ? err.message : 'Move failed.');
      });
  };

  // Only hand TacticalMap a defined onPickPosition while a position-shaped
  // technique is actually selected (#2206) — TacticalMap treats the prop's
  // mere presence as "picking is active" for its highlight styling, so
  // passing undefined here keeps today's move-only behavior byte-for-byte
  // whenever no position-shaped technique is selected.
  const isPositionPickActive = positionShape !== 'none' && onPickPosition !== undefined;

  // GM-place target picker (#3385): value = the co-located object's ObjectDB
  // pk — participant.character_sheet_id (CharacterSheet/ObjectDB share a pk,
  // see root CLAUDE.md) or opponent.objectdb_id (already serialized).
  const placeTargets = [
    ...(encounter.participants ?? [])
      .filter((p) => p.character_sheet_id != null)
      .map((p) => ({ id: p.character_sheet_id, name: p.character_name })),
    ...(encounter.opponents ?? [])
      .filter((o) => o.objectdb_id != null)
      .map((o) => ({ id: o.objectdb_id as number, name: o.name })),
  ];

  const handleGMPlace = (positionId: number): boolean => {
    if (placeTargetId == null) {
      return false;
    }
    const action = gmPlaceActions.find((a) => a.ref.position_id === positionId);
    if (!action) {
      return false;
    }
    dispatchAction({ ref: action.ref, kwargs: { target_object_id: placeTargetId } })
      .then((result) => {
        if (isDispatchFailure(result)) {
          toast.error(result.message ?? 'Placement rejected.');
          return;
        }
        setPlaceTargetId(null);
        queryClient
          .invalidateQueries({ queryKey: combatKeys.encounter(encounterId) })
          .catch(() => {});
      })
      .catch((err: unknown) => {
        toast.error(err instanceof Error ? err.message : 'Placement failed.');
      });
    return true;
  };

  return (
    <div
      className="h-[480px] rounded-lg border border-border bg-card"
      data-testid="combat-tactical-map"
    >
      {gmPlaceActions.length > 0 && (
        <div className="flex items-center gap-2 border-b border-border p-2">
          <Button
            type="button"
            variant={isPlacing ? 'default' : 'outline'}
            size="sm"
            data-testid="gm-place-toggle"
            onClick={() => {
              setIsPlacing((prev) => !prev);
              setPlaceTargetId(null);
            }}
          >
            Place
          </Button>
          {isPlacing && (
            <Select
              value={placeTargetId !== null ? String(placeTargetId) : ''}
              onValueChange={(v) => setPlaceTargetId(v === '' ? null : Number(v))}
            >
              <SelectTrigger className="h-8 w-48 text-xs" data-testid="gm-place-target-select">
                <SelectValue placeholder="Select a target…" />
              </SelectTrigger>
              <SelectContent>
                {placeTargets.map((target) => (
                  <SelectItem key={target.id} value={String(target.id)}>
                    {target.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        </div>
      )}
      <TacticalMap
        nodes={encounter.position_nodes ?? []}
        edges={encounter.position_edges ?? []}
        occupantsByPosition={occupantsByPosition}
        moveActions={moveActions}
        onDispatchMove={handleDispatchMove}
        onPickPosition={isPositionPickActive ? onPickPosition : undefined}
        onGMPlace={isPlacing && placeTargetId != null ? handleGMPlace : undefined}
      />
    </div>
  );
}

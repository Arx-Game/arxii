/**
 * CombatTacticalMap — spatial rendering of the encounter's Position graph
 * (#2006), the main-column view of a fight (CombatMainMap sets its height)
 * (CombatRail renders in-scene on /scenes/:id — #2197). Drawn by BattleMap
 * (#4670): places as areas of squares, combatants as tokens on squares.
 *
 * Occupants are built from participants'/opponents' current_position, plus
 * (#3557) non-combatant scene personas from the scene's persona_positions,
 * drawn dimmed as bystanders: during an encounter this is the page's only
 * map. Click-to-move reuses the same single-hop move_to_position/
 * take_position PlayerActions the scene view uses.
 */

import { useMemo } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { combatKeys, useCombatEncounter, useDispatchPlayerAction } from '../queries';
import { isDispatchFailure } from '../types';
import type { EncounterDetail, RoundActionTyped } from '../types';
import { availableActionsKeys, useAvailableActionsQuery } from '@/scenes/actionQueries';
import { fetchScene, sceneKeys } from '@/scenes/queries';
import type { SceneDetail } from '@/scenes/types';
import { GMPlacementControls } from '@/areas/components/GMPlacementControls';
import type { OccupantLink } from '@/areas/components/TacticalMap';
import type { OccupantMark } from '@/areas/components/PositionMapNode';
import type { ActionRef, PlayerAction } from '@/scenes/actionTypes';
import { BattleMap } from './BattleMap';
import type { BattleOccupant } from './BattleMap';
import type { Square } from '../battleMapLayout';
import type { PositionTargetShape } from '@/actions/types';
import { hopsLeftLine, isMoveAction } from '../roundActionHelpers';

/** Standing on another square of one's own place: free, never in the actions list (#4670). */
const STEP_TO_SQUARE_REF: ActionRef = {
  backend: 'registry',
  registry_key: 'step_to_square',
  challenge_instance_id: null,
  approach_id: null,
  technique_id: null,
};

const ALLY_ALLEGIANCE = 'ally';

function squareKwargs(square: Square | null): Record<string, number> {
  return square ? { square_x: square.x, square_y: square.y } : {};
}

export interface CombatTacticalMapProps {
  /**
   * The scene this encounter belongs to (#3557). The map reads the page's own
   * cached scene detail (same `sceneKeys.detail` key SceneDetailPage fetches)
   * to draw non-combatant personas as bystanders; during an encounter this is
   * the page's only map, so onlookers must not vanish from the room.
   */
  sceneId: number;
  encounterId: number;
  characterId: number;
  /**
   * Cast-time position-targeting shape for the currently selected focused
   * technique (#2206), held by CombatPickProvider (combat/combatPick.ts) so
   * this map can highlight pickable nodes and consume clicks while a
   * position-shaped technique is selected in the rail's "Your Turn" tab. Defaults to 'none'
   * (today's move-only behavior) when the caller omits it.
   */
  positionShape?: PositionTargetShape;
  /**
   * Called when the player clicks a map node while `positionShape !== 'none'`.
   * Only forwarded to BattleMap when picking is active — see the
   * presence-gated `onPickPosition` handoff below.
   */
  onPickPosition?: (positionId: number) => boolean;
}

/**
 * Per-combatant status marks the encounter already knows (#3555), keyed by
 * `p-<participant id>` / `o-<opponent id>`: engagement locks for both sides
 * of the pair, and the declared cover maneuver for coverer and covered ally.
 * Cover comes from `current_round_actions`, which the backend already scopes
 * (own covenant, GM, staff), so this shows exactly what the list shows.
 */
function buildOccupantMarks(encounter: EncounterDetail): Map<string, OccupantMark[]> {
  const marks = new Map<string, OccupantMark[]>();
  const add = (key: string, mark: OccupantMark) => {
    marks.set(key, [...(marks.get(key) ?? []), mark]);
  };
  const participants = encounter.participants ?? [];
  const opponents = encounter.opponents ?? [];

  for (const lock of encounter.engagement_locks ?? []) {
    const pc = participants.find((p) => p.id === lock.participant_id);
    const npc = opponents.find((o) => o.id === lock.opponent_id);
    if (!pc || !npc) continue;
    add(`p-${pc.id}`, { kind: 'locked', title: `${pc.character_name}: locked with ${npc.name}` });
    add(`o-${npc.id}`, { kind: 'locked', title: `${npc.name}: locked with ${pc.character_name}` });
  }

  for (const raw of encounter.current_round_actions ?? []) {
    const action = raw as RoundActionTyped;
    if (action.maneuver !== 'cover' || action.focused_ally_target == null) continue;
    const coverer = participants.find((p) => p.id === action.participant);
    const ally = participants.find((p) => p.id === action.focused_ally_target);
    if (!coverer || !ally) continue;
    add(`p-${coverer.id}`, {
      kind: 'covering',
      title: `${coverer.character_name}: covering ${ally.character_name}`,
    });
    add(`p-${ally.id}`, {
      kind: 'covered',
      title: `${ally.character_name}: covered by ${coverer.character_name}`,
    });
  }
  return marks;
}

/** Engagement locks as position-to-position links for the map overlay (#3555). */
function buildLockLinks(encounter: EncounterDetail): OccupantLink[] {
  const participants = encounter.participants ?? [];
  const opponents = encounter.opponents ?? [];
  const links: OccupantLink[] = [];
  for (const lock of encounter.engagement_locks ?? []) {
    const pc = participants.find((p) => p.id === lock.participant_id);
    const npc = opponents.find((o) => o.id === lock.opponent_id);
    if (!pc?.current_position || !npc?.current_position) continue;
    links.push({
      id: `lock-${lock.id}`,
      positionAId: pc.current_position.id,
      positionBId: npc.current_position.id,
      label: `${pc.character_name} locked with ${npc.name}`,
    });
  }
  return links;
}

/**
 * Non-combatant scene personas at their persona position (#3557): everyone in
 * `scene.personas` whose character is neither a participant (by
 * `character_sheet_id`) nor an opponent (by `objectdb_id`). A persona with no
 * character or no position is skipped.
 */
function combatantCharacterIds(encounter: EncounterDetail): Set<number> {
  const ids = new Set<number>();
  for (const participant of encounter.participants ?? []) {
    if (participant.character_sheet_id != null) ids.add(participant.character_sheet_id);
  }
  for (const opponent of encounter.opponents ?? []) {
    if (opponent.objectdb_id != null) ids.add(opponent.objectdb_id);
  }
  return ids;
}

function buildBystanders(
  encounter: EncounterDetail,
  scene: SceneDetail | undefined,
  characterId: number
): Map<number, BattleOccupant[]> {
  const map = new Map<number, BattleOccupant[]>();
  if (!scene) return map;
  const combatantIds = combatantCharacterIds(encounter);
  const personaById = new Map((scene.personas ?? []).map((p) => [p.id, p]));
  for (const pp of scene.persona_positions ?? []) {
    if (pp.position === null) continue;
    const persona = personaById.get(pp.persona_id);
    if (!persona || persona.character_sheet == null) continue;
    if (combatantIds.has(persona.character_sheet)) continue;
    const occupants = map.get(pp.position.id) ?? [];
    occupants.push({
      name: persona.name,
      bystander: true,
      side: 'bystander',
      square:
        pp.square_x != null && pp.square_y != null ? { x: pp.square_x, y: pp.square_y } : null,
      isViewer: persona.character_sheet === characterId,
    });
    map.set(pp.position.id, occupants);
  }
  return map;
}

export function CombatTacticalMap({
  sceneId,
  encounterId,
  characterId,
  positionShape = 'none',
  onPickPosition,
}: CombatTacticalMapProps) {
  const { data: encounter } = useCombatEncounter(encounterId);

  const { data: scene } = useQuery<SceneDetail>({
    queryKey: sceneKeys.detail(sceneId),
    queryFn: () => fetchScene(String(sceneId)),
    enabled: sceneId > 0,
  });

  const { data: actionsData } = useAvailableActionsQuery(characterId, {
    refetchInterval: 10_000,
  });

  const availableActions: PlayerAction[] = actionsData?.results ?? [];
  const moveActions = availableActions.filter(
    (a) =>
      isMoveAction(a) || (a.ref.backend === 'registry' && a.ref.registry_key === 'take_position')
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

  // Both sources feed this one map (#3557): combatants from the encounter,
  // bystanders from the scene. A bystander viewing the page moves through this
  // map too, so a move or a GM placement refreshes both.
  const refreshMapSources = () => {
    queryClient.invalidateQueries({ queryKey: combatKeys.encounter(encounterId) }).catch(() => {});
    queryClient.invalidateQueries({ queryKey: sceneKeys.detail(sceneId) }).catch(() => {});
    // The hops line and move targets come from the available actions.
    queryClient
      .invalidateQueries({ queryKey: availableActionsKeys.forCharacter(characterId) })
      .catch(() => {});
  };

  const occupantsByPosition = useMemo(() => {
    const map = new Map<number, BattleOccupant[]>();
    if (!encounter) return map;
    const marks = buildOccupantMarks(encounter);
    for (const participant of encounter.participants ?? []) {
      if (participant.current_position) {
        const occupants = map.get(participant.current_position.id) ?? [];
        occupants.push({
          name: participant.character_name,
          thumbnailUrl: participant.thumbnail_url,
          thumbnailMediaUrl: participant.thumbnail_media_url,
          marks: marks.get(`p-${participant.id}`),
          side: 'ally',
          square: participant.current_square,
          isViewer: participant.character_sheet_id === characterId,
        });
        map.set(participant.current_position.id, occupants);
      }
    }
    for (const opponent of encounter.opponents ?? []) {
      if (opponent.current_position) {
        const occupants = map.get(opponent.current_position.id) ?? [];
        occupants.push({
          name: opponent.name,
          thumbnailUrl: opponent.thumbnail_url,
          thumbnailMediaUrl: opponent.thumbnail_media_url,
          marks: marks.get(`o-${opponent.id}`),
          side: opponent.allegiance === ALLY_ALLEGIANCE ? 'ally' : 'enemy',
          square: opponent.current_square,
        });
        map.set(opponent.current_position.id, occupants);
      }
    }
    for (const [positionId, bystanders] of buildBystanders(encounter, scene, characterId)) {
      map.set(positionId, [...(map.get(positionId) ?? []), ...bystanders]);
    }
    return map;
  }, [encounter, scene, characterId]);

  // The viewer's own place: a click on one of its squares is a free step.
  const ownPositionId = useMemo(() => {
    for (const [positionId, occupants] of occupantsByPosition) {
      if (occupants.some((o) => o.isViewer)) return positionId;
    }
    return null;
  }, [occupantsByPosition]);

  const lockLinks = useMemo(() => (encounter ? buildLockLinks(encounter) : []), [encounter]);

  if (!encounter) {
    return (
      <div className="p-4 text-sm text-muted-foreground" data-testid="combat-tactical-map-loading">
        Loading map…
      </div>
    );
  }

  const dispatchMove = (ref: ActionRef, square: Square | null) => {
    dispatchAction({ ref, kwargs: squareKwargs(square) })
      .then((result) => {
        if (isDispatchFailure(result)) {
          toast.error(result.message ?? 'Move rejected.');
          return;
        }
        // A move into held ground ends there; the server's line says so (#4663).
        if (result.message) toast.success(result.message);
        refreshMapSources();
      })
      .catch((err: unknown) => {
        toast.error(err instanceof Error ? err.message : 'Move failed.');
      });
  };
  const handleDispatchMove = (action: PlayerAction, square: Square | null) => {
    dispatchMove(action.ref, square);
  };
  const handleStepToSquare = (square: Square) => {
    dispatchMove(STEP_TO_SQUARE_REF, square);
  };

  // Only hand BattleMap a defined onPickPosition while a position-shaped
  // technique is actually selected (#2206) — BattleMap treats the prop's
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

  // The viewer's hops left this round (#4608), off the moves the server offers.
  const hopsLine = hopsLeftLine(moveActions);

  return (
    <div
      className="relative flex h-full flex-col overflow-hidden rounded-lg border border-border bg-card"
      data-testid="combat-tactical-map"
    >
      {hopsLine !== null && (
        <p
          className="absolute right-2 top-2 z-10 rounded bg-background/80 px-2 py-0.5 text-xs text-muted-foreground"
          data-testid="map-hops-left"
        >
          {hopsLine}
        </p>
      )}
      <GMPlacementControls
        gmPlaceActions={gmPlaceActions}
        targets={placeTargets}
        dispatchAction={dispatchAction}
        onPlaced={() => {
          refreshMapSources();
        }}
      >
        {(onGMPlace) => (
          <BattleMap
            nodes={encounter.position_nodes ?? []}
            edges={encounter.position_edges ?? []}
            occupantsByPosition={occupantsByPosition}
            heldPositions={encounter.held_positions ?? []}
            telegraphs={(encounter.pending_attacks ?? [])
              .filter((a) => !a.cancelled && a.covered_position_id !== null)
              .map((a) => ({
                id: a.id,
                positionId: a.covered_position_id as number,
                attackName: a.attack_name,
                roundsUntilLanding: a.rounds_until_landing,
              }))}
            links={lockLinks}
            moveActions={moveActions}
            ownPositionId={ownPositionId}
            onDispatchMove={handleDispatchMove}
            onStepToSquare={handleStepToSquare}
            onPickPosition={isPositionPickActive ? onPickPosition : undefined}
            onGMPlace={onGMPlace}
          />
        )}
      </GMPlacementControls>
    </div>
  );
}

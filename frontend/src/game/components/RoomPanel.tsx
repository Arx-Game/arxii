import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useGameSocket } from '@/hooks/useGameSocket';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { startScene, finishScene } from '@/scenes/queries';
import { useAppDispatch, useAppSelector } from '@/store/hooks';
import { setSessionScene, type RoomStateResyncStatus } from '@/store/gameSlice';
import type { HubTidings, NpcGiver, RoomStateObject, SceneSummary } from '@/hooks/types';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { dispatchRoomBuilder } from '@/buildings/api';
import { buildingKeys, useBuildingForRoomQuery } from '@/buildings/queries';
import { BuildingBuilderDialog } from '@/buildings/components/BuildingBuilderDialog';
import { RitualProposedChip } from '@/rituals/components/RitualProposedChip';
import { RoomHeader } from './room-panel/RoomHeader';
import { RoomDescription } from './room-panel/RoomDescription';
import { CharactersList } from './room-panel/CharactersList';
import { ExitsList } from './room-panel/ExitsList';
import { PortalsBlock } from './room-panel/PortalsBlock';
import { TrapsBlock } from './room-panel/TrapsBlock';
import { ObjectsList } from './room-panel/ObjectsList';
import { NpcGiversBlock } from './room-panel/NpcGiversBlock';
import { RoomEditorPanel } from './room-panel/RoomEditorPanel';
import { HubTidingsPanel } from './room-panel/HubTidingsPanel';
import { BoardPanel } from '@/boards/components/BoardPanel';
import { useBoardForRoomQuery } from '@/boards/queries';
import { RoomAuraPicker } from './room-panel/RoomAuraPicker';
import { SceneHighlightsPanel } from './room-panel/SceneHighlightsPanel';

/** Resolves the room's LOCATION board and renders it once loaded (#3286). */
function RoomBoardPanel({
  roomProfileId,
  characterId,
}: {
  roomProfileId: number;
  characterId?: number | null;
}) {
  const { data: board } = useBoardForRoomQuery(roomProfileId);
  if (!board) return null;
  return <BoardPanel boardId={board.id} boardName={board.name} characterId={characterId} />;
}

export interface RoomData {
  id: number;
  name: string;
  description: string;
  thumbnail_url: string | null;
  characters: RoomStateObject[];
  objects: RoomStateObject[];
  exits: RoomStateObject[];
  decorations?: string[];
  comfort_level?: number;
  is_owner: boolean;
  is_public: boolean;
  hub: HubTidings | null;
  /** Active NPC placements standing in this room (#3044); absent on older fixtures. */
  npc_givers?: NpcGiver[];
  /** #3288 — true when ANY occupant is concealed. Identity-free OOC disclosure. */
  has_unseen_presence?: boolean;
}

interface RoomPanelProps {
  character: string | null;
  /** The active puppet's ObjectDB pk, for owner-gated room editing (#1470). */
  characterId?: number | null;
  room: RoomData | null;
  scene: SceneSummary | null;
  onCharacterClick?: (character: RoomStateObject) => void;
  /** True when the scene's room has an active CombatEncounter (#2157). */
  hasActiveEncounter?: boolean;
  /** True when the scene's room has an active Battle (#2157). */
  hasActiveBattle?: boolean;
  /** The viewer's active RosterEntry pk — threads to the hub wanted board (#1826). */
  viewerEntryId?: number | null;
  /** The viewer's active persona pk — the unseen-presence report identity (#3288). */
  viewerPersonaId?: number | null;
  /** The viewer's own portrait for the "you" row (#3856); null shows initials. */
  viewerThumbnailUrl?: string | null;
}

function RoomLocationRecovery({
  character,
  isConnected,
  status,
  error,
  requestRoomState,
  connect,
  send,
}: {
  character: string | null;
  isConnected: boolean;
  status: RoomStateResyncStatus;
  error?: string;
  requestRoomState: (character: string) => void;
  connect: (character: string) => Promise<unknown>;
  send: (character: string, command: string) => void;
}) {
  const locationTitle = character
    ? 'Location not confirmed yet'
    : 'Choose a character to enter the world';
  let locationCopy = 'Select a character above to see room information.';
  if (character) {
    locationCopy = isConnected
      ? `Connected as ${character}, but the game has not confirmed your location yet.`
      : `${character} is selected, but the game connection is not ready.`;
  }
  let retryLabel = 'Reconnect';
  if (status === 'pending') retryLabel = 'Refreshing location…';
  else if (isConnected) retryLabel = 'Refresh location';
  const retryLocation = () => {
    if (!character) return;
    if (isConnected) requestRoomState(character);
    else void connect(character).catch(() => {});
  };
  return (
    <div
      className="flex flex-col gap-3 p-4 text-sm"
      role={status === 'failure' ? 'alert' : 'status'}
    >
      <div>
        <h3 className="font-semibold">{locationTitle}</h3>
        <p className="mt-1 text-muted-foreground">{locationCopy}</p>
      </div>
      {character && (
        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={retryLocation}
            disabled={status === 'pending'}
          >
            {retryLabel}
          </Button>
          {isConnected && (
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => send(character, `@ic ${character}`)}
            >
              Re-enter as {character}
            </Button>
          )}
          <Link
            to="/hall"
            className="inline-flex min-h-9 items-center rounded-md border px-3 text-sm font-medium"
          >
            Return to Hall
          </Link>
        </div>
      )}
      {status !== 'idle' && (
        <p className="text-xs text-muted-foreground" aria-live="polite">
          {status === 'pending' && 'Waiting for the location response…'}
          {status === 'success' && 'Location refreshed.'}
          {status === 'partial' && 'Location arrived, but confirmation was lost. Try again.'}
          {status === 'failure' && (error ?? 'Location refresh failed. Try again.')}
        </p>
      )}
    </div>
  );
}

function TenancyAction({
  characterId,
  isOwner,
  buildingId,
  isTenant,
  isPrimaryHome,
  setHomePending,
  onSetHome,
}: {
  characterId: number;
  isOwner: boolean;
  buildingId?: number | null;
  isTenant?: boolean;
  isPrimaryHome?: boolean;
  setHomePending: boolean;
  onSetHome: () => void;
}) {
  const [builderOpen, setBuilderOpen] = useState(false);
  if (isOwner && buildingId != null) {
    return (
      <div className="border-b p-2">
        <Button variant="outline" size="sm" className="w-full" onClick={() => setBuilderOpen(true)}>
          Manage Building
        </Button>
        <BuildingBuilderDialog
          buildingId={buildingId}
          characterId={characterId}
          open={builderOpen}
          onOpenChange={setBuilderOpen}
        />
      </div>
    );
  }
  if (isTenant && !isPrimaryHome) {
    return (
      <div className="border-b p-2">
        <Button
          variant="outline"
          size="sm"
          className="w-full"
          disabled={setHomePending}
          onClick={onSetHome}
        >
          Set as Home
        </Button>
      </div>
    );
  }
  return null;
}

export function RoomPanel({
  character,
  characterId,
  room,
  scene,
  onCharacterClick,
  hasActiveEncounter = false,
  hasActiveBattle = false,
  viewerEntryId = null,
  viewerPersonaId = null,
  viewerThumbnailUrl = null,
}: RoomPanelProps) {
  const { send, connect, requestRoomState } = useGameSocket();
  const dispatch = useAppDispatch();
  const session = useAppSelector((state) =>
    character ? state.game.sessions[character] : undefined
  );
  const isConnected = session?.isConnected ?? false;
  const roomStateResyncStatus = session?.roomStateResyncStatus ?? 'idle';
  const roomStateResyncError = session?.roomStateResyncError;
  const queryClient = useQueryClient();
  const [editOpen, setEditOpen] = useState(false);

  // Which building this room belongs to + what the viewer may do here
  // (owner → manage; tenant → set home). Booleans and ids only.
  const forRoom = useBuildingForRoomQuery(room?.id, characterId);

  const setHome = useMutation({
    mutationFn: () => dispatchRoomBuilder(characterId!, 'set_primary_home', {}),
    onSuccess: ({ message, success }) => {
      if (success === false) {
        toast.error(message);
        return;
      }
      toast.success(message);
      if (room) {
        queryClient.invalidateQueries({ queryKey: buildingKeys.forRoom(room.id) });
      }
      if (character) {
        send(character, 'look');
      }
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const start = useMutation({
    mutationFn: () => {
      if (!room || !character) throw new Error('No room or character');
      const name = `${character} scene at ${room.name} on ${new Date().toISOString().slice(0, 10)}`;
      return startScene(room.id, name);
    },
    onSuccess: (data: SceneSummary) => {
      if (character) {
        dispatch(setSessionScene({ character, scene: data }));
      }
    },
  });

  const end = useMutation({
    mutationFn: () => finishScene(String(scene?.id)),
    onSuccess: () => {
      if (character) {
        dispatch(setSessionScene({ character, scene: null }));
      }
    },
  });

  if (!room || !character) {
    return (
      <RoomLocationRecovery
        character={character}
        isConnected={isConnected}
        status={roomStateResyncStatus}
        error={roomStateResyncError}
        requestRoomState={requestRoomState}
        connect={connect}
        send={send}
      />
    );
  }

  const handleExit = (exit: RoomStateObject) => {
    const cmd = exit.commands[0] ?? exit.name;
    send(character, cmd);
  };

  return (
    <div className="flex flex-col gap-0">
      <RoomHeader
        name={room.name}
        scene={scene}
        onStartScene={() => start.mutate()}
        onEndScene={() => end.mutate()}
        isStartPending={start.isPending}
        isEndPending={end.isPending}
        canEdit={Boolean(room.is_owner) && characterId != null}
        onEditRoom={() => setEditOpen(true)}
        hasActiveEncounter={hasActiveEncounter}
        hasActiveBattle={hasActiveBattle}
        onRefreshRoomState={() => requestRoomState(character)}
        roomStateResyncStatus={roomStateResyncStatus}
        roomStateResyncError={roomStateResyncError}
      />

      {scene && <RitualProposedChip sceneId={scene.id} />}

      {room.is_owner && characterId != null && (
        <Dialog open={editOpen} onOpenChange={setEditOpen}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Edit room</DialogTitle>
            </DialogHeader>
            <RoomEditorPanel
              characterId={characterId}
              initialName={room.name}
              initialDescription={room.description}
              initialIsPublic={Boolean(room.is_public)}
              onSaved={() => {
                setEditOpen(false);
                send(character, 'look');
              }}
              onCancel={() => setEditOpen(false)}
            />
          </DialogContent>
        </Dialog>
      )}

      {characterId != null && (
        <TenancyAction
          characterId={characterId}
          isOwner={room.is_owner}
          buildingId={forRoom.data?.building_id}
          isTenant={forRoom.data?.is_tenant}
          isPrimaryHome={forRoom.data?.is_primary_home_here}
          setHomePending={setHome.isPending}
          onSetHome={() => setHome.mutate()}
        />
      )}

      {characterId != null && (forRoom.data?.is_tenant || forRoom.data?.is_owner) && (
        <RoomAuraPicker characterId={characterId} roomId={room.id} />
      )}

      {room.description && <RoomDescription description={room.description} />}
      {(room.decorations?.length || room.comfort_level != null) && (
        <section className="border-b px-3 py-2" aria-label="Room details">
          {room.decorations && room.decorations.length > 0 && (
            <p className="text-xs text-muted-foreground">{room.decorations.join(' · ')}</p>
          )}
          {room.comfort_level != null && (
            <p className="mt-1 text-xs text-muted-foreground">Comfort {room.comfort_level}/10</p>
          )}
        </section>
      )}

      {scene && <SceneHighlightsPanel sceneId={scene.id} />}

      <CharactersList
        characters={room.characters}
        viewer={{ name: character, thumbnailUrl: viewerThumbnailUrl }}
        // `look me` (#3856): what others see when they look at you, as a note
        // in the column. `me` rather than the name, so it can never
        // prefix-match another occupant.
        onViewerClick={() => send(character, 'look me')}
        onCharacterClick={onCharacterClick}
        hasUnseenPresence={Boolean(room.has_unseen_presence)}
        viewerPersonaId={viewerPersonaId}
        viewerInScene={scene?.viewer_entered ?? null}
      />
      <NpcGiversBlock npcGivers={room.npc_givers ?? []} />
      {room.characters.length > 0 && (
        <p className="border-b px-3 py-2 text-xs text-muted-foreground" role="note">
          Select an occupant to open character context and authorized details.
        </p>
      )}
      <ObjectsList objects={room.objects} characterId={characterId} />
      {room.hub && <HubTidingsPanel hub={room.hub} viewerEntryId={viewerEntryId} />}
      {room.hub?.kind === 'NOTICE_BOARD' && (
        <RoomBoardPanel roomProfileId={room.id} characterId={characterId} />
      )}
      <ExitsList exits={room.exits} onExit={handleExit} />
      <PortalsBlock characterId={characterId} />
      <TrapsBlock characterId={characterId} />
      {room.thumbnail_url && (
        <details className="border-t">
          <summary className="cursor-pointer px-3 py-2 text-xs text-muted-foreground">
            Room art
          </summary>
          <img src={room.thumbnail_url} alt={room.name} className="h-32 w-full object-cover" />
        </details>
      )}
    </div>
  );
}

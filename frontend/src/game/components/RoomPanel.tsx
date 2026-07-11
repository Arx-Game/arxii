import { useState } from 'react';
import { useGameSocket } from '@/hooks/useGameSocket';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { startScene, finishScene } from '@/scenes/queries';
import { useAppDispatch } from '@/store/hooks';
import { setSessionScene } from '@/store/gameSlice';
import type { HubTidings, RoomStateObject, SceneSummary } from '@/hooks/types';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { dispatchRoomBuilder } from '@/buildings/api';
import { buildingKeys, useBuildingForRoomQuery } from '@/buildings/queries';
import { BuildingBuilderDialog } from '@/buildings/components/BuildingBuilderDialog';
import { RoomHeader } from './room-panel/RoomHeader';
import { RoomDescription } from './room-panel/RoomDescription';
import { CharactersList } from './room-panel/CharactersList';
import { ExitsList } from './room-panel/ExitsList';
import { ObjectsList } from './room-panel/ObjectsList';
import { RoomEditorPanel } from './room-panel/RoomEditorPanel';
import { HubTidingsPanel } from './room-panel/HubTidingsPanel';
import { RoomAuraPicker } from './room-panel/RoomAuraPicker';
import { SceneHighlightsPanel } from './room-panel/SceneHighlightsPanel';

export interface RoomData {
  id: number;
  name: string;
  description: string;
  thumbnail_url: string | null;
  characters: RoomStateObject[];
  objects: RoomStateObject[];
  exits: RoomStateObject[];
  is_owner: boolean;
  is_public: boolean;
  hub: HubTidings | null;
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
}

export function RoomPanel({
  character,
  characterId,
  room,
  scene,
  onCharacterClick,
  hasActiveEncounter = false,
  hasActiveBattle = false,
}: RoomPanelProps) {
  const { send } = useGameSocket();
  const dispatch = useAppDispatch();
  const queryClient = useQueryClient();
  const [editOpen, setEditOpen] = useState(false);
  const [builderOpen, setBuilderOpen] = useState(false);

  // Which building this room belongs to + what the viewer may do here
  // (owner → manage; tenant → set home). Booleans and ids only.
  const forRoom = useBuildingForRoomQuery(room?.id, characterId);

  const setHome = useMutation({
    mutationFn: () => dispatchRoomBuilder(characterId!, 'set_primary_home', {}),
    onSuccess: (message: string) => {
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
      <div className="p-4 text-sm text-muted-foreground">
        No location data available. Connect a character to see room information.
      </div>
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
      />

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

      {characterId != null &&
        (room.is_owner && forRoom.data?.building_id != null ? (
          <div className="border-b p-2">
            <Button
              variant="outline"
              size="sm"
              className="w-full"
              onClick={() => setBuilderOpen(true)}
            >
              Manage Building
            </Button>
            <BuildingBuilderDialog
              buildingId={forRoom.data.building_id}
              characterId={characterId}
              open={builderOpen}
              onOpenChange={setBuilderOpen}
            />
          </div>
        ) : forRoom.data?.is_tenant && !forRoom.data.is_primary_home_here ? (
          <div className="border-b p-2">
            <Button
              variant="outline"
              size="sm"
              className="w-full"
              disabled={setHome.isPending}
              onClick={() => setHome.mutate()}
            >
              Set as Home
            </Button>
          </div>
        ) : null)}

      {characterId != null && (forRoom.data?.is_tenant || forRoom.data?.is_owner) && (
        <RoomAuraPicker characterId={characterId} roomId={room.id} />
      )}

      {room.thumbnail_url && (
        <div className="border-b">
          <img src={room.thumbnail_url} alt={room.name} className="h-32 w-full object-cover" />
        </div>
      )}

      {room.description && <RoomDescription description={room.description} />}

      {room.hub && <HubTidingsPanel hub={room.hub} />}

      {scene && <SceneHighlightsPanel sceneId={scene.id} />}

      <CharactersList characters={room.characters} onCharacterClick={onCharacterClick} />
      <ExitsList exits={room.exits} onExit={handleExit} />
      <ObjectsList objects={room.objects} />
    </div>
  );
}

import { useGameSocket } from '@/hooks/useGameSocket';
import { useMutation } from '@tanstack/react-query';
import { startScene, finishScene } from '@/scenes/queries';
import { useAppDispatch } from '@/store/hooks';
import { setSessionScene } from '@/store/gameSlice';
import type { RoomStateObject, SceneSummary } from '@/hooks/types';
import { RoomHeader } from './room-panel/RoomHeader';
import { RoomDescription } from './room-panel/RoomDescription';
import { CharactersList } from './room-panel/CharactersList';
import { ExitsList } from './room-panel/ExitsList';
import { ObjectsList } from './room-panel/ObjectsList';

interface RoomData {
  id: number;
  name: string;
  description: string;
  thumbnail_url: string | null;
  characters: RoomStateObject[];
  objects: RoomStateObject[];
  exits: RoomStateObject[];
}

interface RoomPanelProps {
  character: string | null;
  room: RoomData | null;
  scene: SceneSummary | null;
}

export function RoomPanel({ character, room, scene }: RoomPanelProps) {
  const { send } = useGameSocket();
  const dispatch = useAppDispatch();

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
      />

      {room.thumbnail_url && (
        <div className="border-b">
          <img src={room.thumbnail_url} alt={room.name} className="h-32 w-full object-cover" />
        </div>
      )}

      {room.description && <RoomDescription description={room.description} />}

      <CharactersList characters={room.characters} />
      <ExitsList exits={room.exits} onExit={handleExit} />
      <ObjectsList objects={room.objects} />
    </div>
  );
}

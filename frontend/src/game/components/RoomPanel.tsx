import { useState } from 'react';
import { Link } from 'react-router-dom';
import { ChevronDown, ChevronRight, DoorOpen, Package, Users } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Avatar, AvatarImage, AvatarFallback } from '@/components/ui/avatar';
import { useGameSocket } from '@/hooks/useGameSocket';
import { useMutation } from '@tanstack/react-query';
import { startScene, finishScene } from '@/scenes/queries';
import { useAppDispatch } from '@/store/hooks';
import { setSessionScene } from '@/store/gameSlice';
import type { RoomStateObject, SceneSummary } from '@/hooks/types';

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
  const [descriptionExpanded, setDescriptionExpanded] = useState(false);
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
      {/* Room header */}
      <div className="border-b px-3 py-2">
        <h3 className="text-sm font-semibold">{room.name}</h3>
        {scene ? (
          <div className="mt-1 flex items-center gap-2">
            <Link to={`/scenes/${scene.id}`}>
              <Badge variant="secondary" className="text-xs">
                Scene: {scene.name}
              </Badge>
            </Link>
            {scene.is_owner && (
              <Button
                variant="ghost"
                size="sm"
                className="h-5 px-1 text-xs text-destructive"
                onClick={() => end.mutate()}
                disabled={end.isPending}
              >
                End
              </Button>
            )}
          </div>
        ) : (
          <Button
            variant="ghost"
            size="sm"
            className="mt-1 h-6 px-2 text-xs"
            onClick={() => start.mutate()}
            disabled={start.isPending}
          >
            Start Scene
          </Button>
        )}
      </div>

      {/* Room thumbnail */}
      {room.thumbnail_url && (
        <div className="border-b">
          <img src={room.thumbnail_url} alt={room.name} className="h-32 w-full object-cover" />
        </div>
      )}

      {/* Description */}
      {room.description && (
        <div className="border-b px-3 py-2">
          <button
            onClick={() => setDescriptionExpanded(!descriptionExpanded)}
            className="flex w-full items-center gap-1 text-xs font-semibold uppercase text-muted-foreground"
          >
            {descriptionExpanded ? (
              <ChevronDown className="h-3 w-3" />
            ) : (
              <ChevronRight className="h-3 w-3" />
            )}
            Description
          </button>
          {descriptionExpanded && (
            <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{room.description}</p>
          )}
        </div>
      )}

      {/* Characters */}
      <div className="border-b px-3 py-2">
        <div className="mb-1 flex items-center gap-1 text-xs font-semibold uppercase text-muted-foreground">
          <Users className="h-3 w-3" />
          Characters ({room.characters.length})
        </div>
        {room.characters.length > 0 ? (
          <ul className="space-y-1">
            {room.characters.map((char) => (
              <li key={char.dbref} className="flex items-center gap-2">
                <Avatar className="h-5 w-5">
                  {char.thumbnail_url ? (
                    <AvatarImage src={char.thumbnail_url} alt={char.name} />
                  ) : null}
                  <AvatarFallback className="text-[8px]">
                    {char.name.slice(0, 2).toUpperCase()}
                  </AvatarFallback>
                </Avatar>
                <span className="text-xs">{char.name}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-xs text-muted-foreground">Nobody else here.</p>
        )}
      </div>

      {/* Exits */}
      <div className="border-b px-3 py-2">
        <div className="mb-1 flex items-center gap-1 text-xs font-semibold uppercase text-muted-foreground">
          <DoorOpen className="h-3 w-3" />
          Exits
        </div>
        {room.exits.length > 0 ? (
          <div className="flex flex-wrap gap-1">
            {room.exits.map((exit) => (
              <Button
                key={exit.dbref}
                variant="outline"
                size="sm"
                className="h-6 px-2 text-xs"
                onClick={() => handleExit(exit)}
              >
                {exit.name}
              </Button>
            ))}
          </div>
        ) : (
          <p className="text-xs text-muted-foreground">No obvious exits.</p>
        )}
      </div>

      {/* Objects */}
      {room.objects.length > 0 && (
        <div className="px-3 py-2">
          <div className="mb-1 flex items-center gap-1 text-xs font-semibold uppercase text-muted-foreground">
            <Package className="h-3 w-3" />
            Objects ({room.objects.length})
          </div>
          <ul className="space-y-1">
            {room.objects.map((obj) => (
              <li key={obj.dbref} className="flex items-center gap-2">
                {obj.thumbnail_url ? (
                  <img
                    src={obj.thumbnail_url}
                    alt={obj.name}
                    className="h-5 w-5 rounded object-cover"
                  />
                ) : (
                  <div className="h-5 w-5 rounded bg-muted" />
                )}
                <span className="text-xs">{obj.name}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

import { Card, CardContent } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { useGameSocket } from '../../hooks/useGameSocket';
import type { RoomStateObject } from '../../hooks/types';
import type { MyRosterEntry } from '../../roster/types';

interface LocationWindowProps {
  character: MyRosterEntry['name'];
  room: {
    id: number;
    name: string;
    thumbnail_url: string | null;
    objects: RoomStateObject[];
    exits: RoomStateObject[];
  } | null;
}

export function LocationWindow({ character, room }: LocationWindowProps) {
  const { send } = useGameSocket();
  if (!room) return null;

  const handleExit = (exit: RoomStateObject) => {
    const cmd = exit.commands[0] ?? exit.name;
    send(character, cmd);
  };

  return (
    <Card className="mb-4">
      <CardContent className="p-4">
        <h2 className="mb-2 text-lg font-semibold">{room.name}</h2>
        {room.thumbnail_url && (
          <img src={room.thumbnail_url} alt={room.name} className="mb-4 w-full rounded" />
        )}
        {room.objects.length > 0 && (
          <div className="mb-4">
            <h3 className="mb-2 text-sm font-semibold">Here</h3>
            <div className="flex flex-wrap gap-2">
              {room.objects.map((obj) => (
                <div key={obj.dbref} className="flex items-center gap-1 text-sm">
                  {obj.thumbnail_url ? (
                    <img src={obj.thumbnail_url} alt={obj.name} className="h-6 w-6 rounded" />
                  ) : (
                    <div className="h-6 w-6 rounded bg-muted" />
                  )}
                  <span>{obj.name}</span>
                </div>
              ))}
            </div>
          </div>
        )}
        <div>
          <h3 className="mb-2 text-sm font-semibold">Exits</h3>
          {room.exits.length > 0 ? (
            <div className="flex flex-wrap gap-2">
              {room.exits.map((exit) => (
                <Button key={exit.dbref} size="sm" onClick={() => handleExit(exit)}>
                  {exit.name}
                </Button>
              ))}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">No obvious exits.</p>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

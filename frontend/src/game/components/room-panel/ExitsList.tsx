import { DoorOpen } from 'lucide-react';
import { Button } from '@/components/ui/button';
import type { RoomStateObject } from '@/hooks/types';

interface ExitsListProps {
  exits: RoomStateObject[];
  onExit: (exit: RoomStateObject) => void;
}

export function ExitsList({ exits, onExit }: ExitsListProps) {
  return (
    <div className="border-b px-3 py-2">
      <div className="mb-1 flex items-center gap-1 text-xs font-semibold uppercase text-muted-foreground">
        <DoorOpen className="h-3 w-3" />
        Exits
      </div>
      {exits.length > 0 ? (
        <div className="flex flex-wrap gap-1">
          {exits.map((exit) => (
            <Button
              key={exit.dbref}
              variant="outline"
              size="sm"
              className="h-6 px-2 text-xs"
              onClick={() => onExit(exit)}
            >
              {exit.name}
            </Button>
          ))}
        </div>
      ) : (
        <p className="text-xs text-muted-foreground">No obvious exits.</p>
      )}
    </div>
  );
}

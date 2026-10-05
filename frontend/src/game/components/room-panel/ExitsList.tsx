import { DoorOpen } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { TargetMenu } from '@/game/target-menu/TargetMenu';
import { dbrefToId } from '@/lib/dbref';
import type { RoomStateObject } from '@/hooks/types';

interface ExitsListProps {
  exits: RoomStateObject[];
  onExit: (exit: RoomStateObject) => void;
  partition: string;
  actorId: number | null;
}

export function ExitsList({ exits, onExit, partition, actorId }: ExitsListProps) {
  return (
    <div className="border-b px-3 py-2">
      <div className="mb-1 flex items-center gap-1 text-xs font-semibold uppercase text-muted-foreground">
        <DoorOpen className="h-3 w-3" />
        Exits
      </div>
      {exits.length > 0 ? (
        <div className="flex flex-wrap gap-1">
          {exits.map((exit) => (
            <TargetMenu
              key={exit.dbref}
              partition={partition}
              actorId={actorId}
              target={{ kind: 'exits', target_id: dbrefToId(exit.dbref) }}
            >
              <Button
                variant="outline"
                size="sm"
                className="min-h-11 px-3 text-xs"
                onClick={() => onExit(exit)}
              >
                {exit.name}
              </Button>
            </TargetMenu>
          ))}
        </div>
      ) : (
        <p className="text-xs text-muted-foreground">No obvious exits.</p>
      )}
    </div>
  );
}

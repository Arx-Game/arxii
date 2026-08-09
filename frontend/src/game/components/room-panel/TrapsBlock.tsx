/**
 * TrapsBlock (#3011) — room-sidebar list of armed traps the active character
 * can currently see, with a Disarm affordance.
 *
 * Reads `useRoomTrapsQuery` (`src/room_features/queries.ts`), which hits
 * `GET /api/room-features/traps/?character_id=` — already leak-safe server
 * side (armed, plus not-hidden or already detected by this character; see
 * `RoomTrapViewSet`) — this component adds no filtering of its own and
 * renders nothing when the query is disabled or the list is empty (mirrors
 * `PortalsBlock`'s shape).
 *
 * Disarm dispatches the same `disarm_trap` registry action telnet's `disarm`
 * command uses (`DisarmTrapAction`). A failed disarm still fires the trap on
 * the would-be disarmer — its consequence message is the same
 * `DispatchResult.message` a success carries, so both surface via a toast.
 */

import { useQueryClient } from '@tanstack/react-query';
import { AlertTriangle } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { useDispatchPlayerAction } from '@/combat/queries';
import { isDispatchFailure } from '@/combat/types';
import { roomTrapKeys, useRoomTrapsQuery } from '@/room_features/queries';

interface TrapsBlockProps {
  /** The active puppet's ObjectDB/CharacterSheet pk, or null/undefined with none active. */
  characterId?: number | null;
}

export function TrapsBlock({ characterId }: TrapsBlockProps) {
  const { data: traps = [] } = useRoomTrapsQuery(characterId);
  const { mutate, isPending } = useDispatchPlayerAction(characterId ?? 0);
  const queryClient = useQueryClient();

  if (traps.length === 0) {
    return null;
  }

  const disarm = (trapId: number) => {
    mutate(
      {
        ref: { backend: 'registry', registry_key: 'disarm_trap' },
        kwargs: { trap_id: trapId },
      },
      {
        onSuccess: (result) => {
          if (result.message) {
            if (isDispatchFailure(result)) {
              toast.error(result.message);
            } else {
              toast.success(result.message);
            }
          }
          if (characterId != null) {
            queryClient.invalidateQueries({ queryKey: roomTrapKeys.forCharacter(characterId) });
          }
        },
        onError: (error: Error) => toast.error(error.message),
      }
    );
  };

  return (
    <div className="border-b px-3 py-2" data-testid="traps-block">
      <div className="mb-1 flex items-center gap-1 text-xs font-semibold uppercase text-muted-foreground">
        <AlertTriangle className="h-3 w-3" />
        Traps ({traps.length})
      </div>
      <ul className="space-y-1">
        {traps.map((trap) => (
          <li key={trap.id} className="flex items-center justify-between gap-2 text-xs">
            <span>
              <span className="font-medium">{trap.name}</span>{' '}
              <span className="text-muted-foreground">
                {trap.is_armed ? '(armed)' : '(disarmed)'}
              </span>
            </span>
            {trap.is_armed && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="h-6 shrink-0 px-2 text-xs"
                disabled={isPending}
                onClick={() => disarm(trap.id)}
                data-testid={`trap-disarm-${trap.id}`}
              >
                Disarm
              </Button>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * PortalsBlock (#2222 Task 5) — room-sidebar list of anchors the active
 * character could portal-travel to right now.
 *
 * Reads `usePortalDestinationsQuery` (`src/locations/queries.ts`), which is
 * disabled without a character id and hits
 * `GET /api/locations/portal-destinations/?character_id=` (Task 4). That
 * endpoint already applies the full leak-safe visibility contract server
 * side (kinds narrowed to the character's known travel techniques; a locked
 * anchor visible only with owner/tenant standing; the current room's own
 * anchors excluded) — this component adds no filtering of its own and
 * renders nothing when the query is disabled or the list is empty, so
 * players without the gift/without reachable anchors never see this block.
 *
 * "Travel" dispatches the same `travel_to` registry action the #2163
 * Go-there buttons use (`PresencePanel.tsx`) — the portal branch lives
 * server-side inside `TravelAction`, so the web dispatch is unchanged; only
 * the destination room id differs (the anchor's `room_id`).
 */

import { Sparkles } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { usePortalDestinationsQuery } from '@/locations/queries';
import { useDispatchPlayerAction } from '@/combat/queries';

interface PortalsBlockProps {
  /** The active puppet's ObjectDB/CharacterSheet pk, or null/undefined with none active. */
  characterId?: number | null;
}

export function PortalsBlock({ characterId }: PortalsBlockProps) {
  const { data: destinations = [] } = usePortalDestinationsQuery(characterId);
  const { mutate, isPending } = useDispatchPlayerAction(characterId ?? 0);

  if (destinations.length === 0) {
    return null;
  }

  const dispatchTravel = (roomId: number) => {
    mutate({
      ref: { backend: 'registry', registry_key: 'travel_to' },
      kwargs: { target: roomId },
    });
  };

  return (
    <div className="border-b px-3 py-2" data-testid="portals-block">
      <div className="mb-1 flex items-center gap-1 text-xs font-semibold uppercase text-muted-foreground">
        <Sparkles className="h-3 w-3" />
        Portals
      </div>
      <ul className="space-y-1">
        {destinations.map((dest) => (
          <li key={dest.anchor_id} className="flex items-center justify-between gap-2 text-xs">
            <span>
              <span className="font-medium">{dest.kind_name}</span>{' '}
              <span className="text-muted-foreground">
                — {dest.anchor_name}, {dest.room_name}
              </span>
            </span>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-6 shrink-0 px-2 text-xs"
              disabled={isPending}
              onClick={() => dispatchTravel(dest.room_id)}
              data-testid={`portal-travel-${dest.anchor_id}`}
            >
              Travel
            </Button>
          </li>
        ))}
      </ul>
    </div>
  );
}

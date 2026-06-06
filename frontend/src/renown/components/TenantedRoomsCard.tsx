import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import type { TenantedRoom } from '../types';

interface Props {
  rooms: TenantedRoom[];
}

/**
 * Tenanted rooms — per-room polish breakdown for rooms this persona
 * tenants. Symmetric with `OwnedDwellingsCard`; no upkeep/dormancy here
 * because those are building-level concepts.
 */
export function TenantedRoomsCard({ rooms }: Props) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Tenanted Rooms</CardTitle>
      </CardHeader>
      <CardContent>
        {rooms.length === 0 ? (
          <p className="text-sm text-muted-foreground">This persona tenants no rooms.</p>
        ) : (
          <ul className="space-y-4 text-sm">
            {rooms.map((room) => (
              <li key={room.id} className="border-b pb-3 last:border-b-0">
                <div className="font-semibold">{room.name}</div>
                {room.polish_by_category.length === 0 ? (
                  <p className="mt-1 text-xs text-muted-foreground">No polish recorded yet.</p>
                ) : (
                  <ul className="mt-2 space-y-1 text-xs">
                    {room.polish_by_category.map((row) => (
                      <li
                        key={row.category_id}
                        className="flex items-baseline justify-between gap-2"
                      >
                        <span>
                          {row.tier_label !== null && (
                            <span className="mr-1 font-medium">{row.tier_label}</span>
                          )}
                          <span className="text-muted-foreground">{row.category_name}</span>
                        </span>
                        <span className="font-mono text-foreground">
                          {row.value.toLocaleString()}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

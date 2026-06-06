import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import type { TenantedRoom } from '../types';
import { PolishCategoryList } from './PolishCategoryList';

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
                <PolishCategoryList rows={room.polish_by_category} />
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

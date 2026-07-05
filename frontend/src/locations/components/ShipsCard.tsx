import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { AlertTriangle } from 'lucide-react';
import type { MyShip } from '../api';

interface Props {
  ships: MyShip[];
}

/**
 * Ships — the persona's owned + covenant-owned vessels (#1446, #1832). Read-only summary:
 * type name, hull/handling/armament, and a repair-needed flag. Commission/upgrade/repair
 * stay on the existing ship action surface — no web write dispatch exists yet, so this
 * card is view-only.
 */
export function ShipsCard({ ships }: Props) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Ships</CardTitle>
      </CardHeader>
      <CardContent>
        {ships.length === 0 ? (
          <p className="text-sm text-muted-foreground">No ships owned or crewed.</p>
        ) : (
          <ul className="space-y-4 text-sm">
            {ships.map((ship) => (
              <li key={ship.id} className="border-b pb-3 last:border-b-0">
                <div className="flex items-baseline justify-between gap-2">
                  <span className="font-semibold">{ship.ship_type.name}</span>
                  {ship.needs_repair && (
                    <Badge variant="destructive" className="gap-1">
                      <AlertTriangle className="h-3 w-3" />
                      Needs repair
                    </Badge>
                  )}
                </div>
                <p className="text-muted-foreground">
                  Hull {ship.effective_hull} · Handling {ship.effective_handling} · Armament{' '}
                  {ship.effective_armament}
                </p>
                {(ship.owner_covenant_name ?? ship.owner_persona_name) && (
                  <p className="text-xs text-muted-foreground">
                    Held by {ship.owner_covenant_name ?? ship.owner_persona_name}
                  </p>
                )}
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

import { useParams } from 'react-router-dom';

import { useRealms } from './queries';

/**
 * Placeholder route element for the Almanach's three staff routes
 * (`/staff/almanach`, `/staff/almanach/realms/:realmId`,
 * `/staff/almanach/houses/:houseId`; #3983 Task 7) — Task 8 replaces this
 * with the realm ladder and house document pages. Exercises the route
 * wiring end to end: reads whichever param is present and looks up the
 * realm name from `useRealms`.
 */
export function AlmanachPage() {
  const { realmId, houseId } = useParams<{ realmId?: string; houseId?: string }>();
  const { data: realms } = useRealms();
  const realm = realmId ? realms?.results.find((r) => r.id === Number(realmId)) : undefined;

  if (houseId) {
    return <div>House {houseId}</div>;
  }
  if (realmId) {
    return <div>{realm?.name ?? `Realm ${realmId}`}</div>;
  }
  return <div>Almanach de Catenys</div>;
}

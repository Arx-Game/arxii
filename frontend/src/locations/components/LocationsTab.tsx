/**
 * LocationsTab (#1446) — the character sheet's consolidated Locations section.
 *
 * Own-only: Dwellings and Tenancies reuse the existing `OwnedDwellingsCard` /
 * `TenantedRoomsCard` from the Renown app (fed by the same `usePersonaRenownQuery` payload —
 * `owned_dwellings` / `tenanted_rooms`), Ships is a new self-scoped read via
 * `useMyShipsQuery`, and Domains is a muted placeholder until #1884/#930 ship an org-owned
 * domain read API.
 *
 * Ships is gated on `isActiveCharacter`: `GET /api/ships/ships/` is server-scoped to the
 * account's ACTIVE persona, not the persona being viewed, so rendering it for a non-active
 * character sheet would show the wrong character's ships. When inactive, the query is
 * disabled (never fetched) and a muted notice renders instead (final review, #1446).
 */

import { Loader2 } from 'lucide-react';

import { usePersonaRenownQuery } from '@/renown/queries';
import { OwnedDwellingsCard } from '@/renown/components/OwnedDwellingsCard';
import { TenantedRoomsCard } from '@/renown/components/TenantedRoomsCard';
import { useMyShipsQuery } from '../queries';
import { ShipsCard } from './ShipsCard';

interface Props {
  /** The viewed character's primary persona pk; null when unresolvable. */
  personaId: number | null;
  /** Whether the viewed character is the viewing account's currently-active character. */
  isActiveCharacter: boolean;
}

export function LocationsTab({ personaId, isActiveCharacter }: Props) {
  const { data: renown, isLoading: renownLoading } = usePersonaRenownQuery(personaId);

  if (personaId === null) {
    return (
      <p className="py-8 text-center text-muted-foreground">
        No active character to view locations for.
      </p>
    );
  }

  if (renownLoading || !renown) {
    return (
      <div className="flex justify-center py-8">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <OwnedDwellingsCard dwellings={renown.owned_dwellings} />
      <TenantedRoomsCard rooms={renown.tenanted_rooms} />
      {isActiveCharacter ? (
        <ShipsSection />
      ) : (
        <p className="text-sm text-muted-foreground" data-testid="ships-foreign-notice">
          Ships are visible while playing this character.
        </p>
      )}
      <p className="text-sm text-muted-foreground" data-testid="domains-placeholder">
        Domains your organizations hold will appear here (#1884).
      </p>
    </div>
  );
}

/**
 * Split out so the ships query is only mounted (and therefore only fetched) when the
 * character being viewed is the account's active character — see module docstring.
 */
function ShipsSection() {
  const { data: ships, isLoading } = useMyShipsQuery();

  if (isLoading) {
    return (
      <div className="flex justify-center py-4">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return <ShipsCard ships={ships ?? []} />;
}

/**
 * LocationsTab (#1446) — the character sheet's consolidated Locations section.
 *
 * Own-only: Dwellings and Tenancies reuse the existing `OwnedDwellingsCard` /
 * `TenantedRoomsCard` from the Renown app (fed by the same `usePersonaRenownQuery` payload —
 * `owned_dwellings` / `tenanted_rooms`), Ships is a new self-scoped read via
 * `useMyShipsQuery`, and Domains is a muted placeholder until #1884/#930 ship an org-owned
 * domain read API.
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
}

export function LocationsTab({ personaId }: Props) {
  const { data: renown, isLoading: renownLoading } = usePersonaRenownQuery(personaId);
  const { data: ships, isLoading: shipsLoading } = useMyShipsQuery();

  if (personaId === null) {
    return (
      <p className="py-8 text-center text-muted-foreground">
        No active character to view locations for.
      </p>
    );
  }

  if (renownLoading || shipsLoading || !renown) {
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
      <ShipsCard ships={ships ?? []} />
      <p className="text-sm text-muted-foreground" data-testid="domains-placeholder">
        Domains your organizations hold will appear here (#1884).
      </p>
    </div>
  );
}

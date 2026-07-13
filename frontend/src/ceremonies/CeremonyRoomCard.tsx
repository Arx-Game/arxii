/**
 * Compact "a rite is underway here" card (#2289).
 *
 * Read-only status for the OPEN ceremony in the viewer's current room; the
 * ceremony verbs ride the generic action dispatch (and telnet). The heavy
 * ceremony UX pass is deferred by spec — this card is deliberately minimal.
 * Renders nothing when no ceremony is open here.
 */

import { useQuery } from '@tanstack/react-query';
import { Flame } from 'lucide-react';
import { apiFetch } from '@/evennia_replacements/api';

interface CeremonyHonoreePayload {
  id: number;
  honoree_name: string;
  prestige_awarded: number;
}

interface CeremonyPayload {
  id: number;
  ceremony_type_name: string;
  officiant_name: string;
  presented_being_name: string;
  status: string;
  honorees: CeremonyHonoreePayload[];
  offering_count: number;
}

async function fetchOpenCeremony(roomId: string): Promise<CeremonyPayload | null> {
  const res = await apiFetch(
    `/api/ceremonies/ceremonies/?status=open&location__objectdb=${roomId}`
  );
  if (!res.ok) {
    throw new Error('Failed to load ceremonies');
  }
  const data = await res.json();
  return data.results?.[0] ?? null;
}

export function CeremonyRoomCard({ roomId }: { roomId: string | undefined }) {
  const { data: ceremony } = useQuery({
    queryKey: ['room-ceremony', roomId],
    queryFn: () => fetchOpenCeremony(roomId!),
    enabled: !!roomId,
    refetchInterval: 30_000,
  });

  if (!ceremony) {
    return null;
  }

  const honorees = ceremony.honorees.map((h) => h.honoree_name).join(', ');

  return (
    <div className="border-b bg-muted/40 px-3 py-2 text-sm">
      <div className="flex items-center gap-2 font-semibold">
        <Flame className="h-4 w-4 text-amber-600" />
        {ceremony.ceremony_type_name} in the name of {ceremony.presented_being_name}
      </div>
      <p className="mt-1 text-xs text-muted-foreground">
        Officiant: {ceremony.officiant_name}
        {honorees ? ` — honoring ${honorees}` : ''}
        {ceremony.offering_count > 0 ? ` — ${ceremony.offering_count} offering(s)` : ''}
      </p>
    </div>
  );
}

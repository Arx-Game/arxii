/**
 * HolySiteBlock (#4333) — the room card's line for a being's shrine here, or the temple the
 * room stands in: Pray, Sacrifice and Pledge yourself, each for that being. Reads
 * `GET /api/worship/beings/holy-site/` for the acting character; renders nothing anywhere
 * that is not holy to a being.
 */

import { Flame } from 'lucide-react';
import { PledgeDialog } from '@/worship/components/PledgeDialog';
import { PrayDialog } from '@/worship/components/PrayDialog';
import { SacrificeDialog } from '@/worship/components/SacrificeDialog';
import { useHolySites } from '@/worship/queries';

interface HolySiteBlockProps {
  /** The active puppet's ObjectDB/CharacterSheet pk, or null/undefined with none active. */
  characterId?: number | null;
  /** The viewer's active RosterEntry pk: the character the site is read for. */
  viewerEntryId?: number | null;
  roomId: number;
}

export function HolySiteBlock({ characterId, viewerEntryId, roomId }: HolySiteBlockProps) {
  const { data: sites = [] } = useHolySites({
    entryId: viewerEntryId ?? undefined,
    roomId,
    enabled: characterId != null,
  });
  if (characterId == null || sites.length === 0) return null;

  return (
    <div className="border-b px-3 py-2" data-testid="holy-site-block">
      {sites.map((site) => (
        <div
          key={`${site.site}-${site.being_id}`}
          className="flex flex-wrap items-center gap-2 text-xs"
        >
          <span className="flex items-center gap-1 font-semibold">
            <Flame className="h-3 w-3 text-amber-600" />
            {site.being_name}&apos;s {site.site}
          </span>
          <span className="ml-auto flex flex-wrap gap-1">
            <PrayDialog characterId={characterId} defaultBeingId={site.being_id} />
            <SacrificeDialog
              characterId={characterId}
              beingId={site.being_id}
              beingName={site.being_name}
            />
            <PledgeDialog characterId={characterId} defaultBeingId={site.being_id} fixedBeing />
          </span>
        </div>
      ))}
    </div>
  );
}

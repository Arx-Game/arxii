import { Megaphone, ScrollText } from 'lucide-react';
import type { HubTidings } from '@/hooks/types';
import { WantedBoard } from '@/justice/components/WantedBoard';

interface HubTidingsPanelProps {
  hub: HubTidings;
  /** The viewer's active RosterEntry pk; null when unknown (wanted board stays read-only). */
  viewerEntryId?: number | null;
}

/** The room's civic-hub tidings: what the notice board carries or the crier calls (#1450). */
export function HubTidingsPanel({ hub, viewerEntryId = null }: HubTidingsPanelProps) {
  const isCrier = hub.kind === 'TOWN_CRIER';
  const Icon = isCrier ? Megaphone : ScrollText;

  return (
    <div className="border-b px-3 py-2">
      <div className="mb-1 flex items-center gap-1 text-xs font-semibold uppercase text-muted-foreground">
        <Icon className="h-3 w-3" />
        {hub.name}
      </div>
      {hub.items.length === 0 ? (
        <p className="text-xs text-muted-foreground">The local tidings are quiet today.</p>
      ) : (
        <ul className="space-y-1">
          {hub.items.map((item, index) => (
            <li key={`${item.occurred_at}-${index}`} className="text-xs">
              <span
                className={
                  item.kind === 'deed'
                    ? 'font-semibold text-emerald-600 dark:text-emerald-400'
                    : 'font-semibold text-rose-600 dark:text-rose-400'
                }
              >
                {item.category ?? (item.kind === 'deed' ? 'Deed' : 'Scandal')}
              </span>{' '}
              <span className="text-muted-foreground">{item.subject}:</span> {item.headline}
            </li>
          ))}
        </ul>
      )}
      {hub.area_id != null && <WantedBoard areaId={hub.area_id} viewerEntryId={viewerEntryId} />}
    </div>
  );
}

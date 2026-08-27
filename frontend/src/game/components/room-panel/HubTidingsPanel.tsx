import { Megaphone, ScrollText } from 'lucide-react';
import type { HubTidings } from '@/hooks/types';
import { WantedBoard } from '@/justice/components/WantedBoard';

// PLACEHOLDER wording (#3412 hygiene fold-in): `item.kind` carries the same lowercase
// FeedItemKind wire values as the tidings feed's PublicFeedItem (see room_state.py's
// `_get_hub`, which serializes `item.kind` straight from the same dataclass), but only
// deed/scandal had labels — the other 7 kinds all fell through to "Scandal", including
// e.g. a birthday tiding. Deliberately plain enum-derived names, not lore-authoritative
// copy; a later design pass can replace them. Keyed as a plain Record (not
// Record<FeedItemKind,...>) because `HubTidingsItem.kind` is hand-typed as a bare
// `string` in hooks/types.ts (a WS payload shape, not generated from the OpenAPI schema).
const HUB_KIND_LABELS: Record<string, string> = {
  deed: 'Deed',
  scandal: 'Scandal',
  pardon: 'Pardon',
  crisis: 'Crisis',
  proclamation: 'Proclamation',
  birthday: 'Birthday',
  stature: 'Stature',
  menace: 'Menace',
  verdict: 'Verdict',
};

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
                {item.category ?? HUB_KIND_LABELS[item.kind] ?? item.kind}
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

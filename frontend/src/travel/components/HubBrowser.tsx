/**
 * HubBrowser — filtered list of travel destinations (#2352).
 *
 * Shows available TravelHubs filtered by the selected travel mode.
 * Used as an embedded picker in VoyagePanel.
 */

import { useTravelHubs } from '../queries';
import type { TravelHub } from '../types';
import { Card } from '@/components/ui/card';

interface HubBrowserProps {
  travelMode: string;
  onSelectHub: (hub: TravelHub) => void;
  selectedHubId?: number;
}

export function HubBrowser({ travelMode, onSelectHub, selectedHubId }: HubBrowserProps) {
  const { data: hubs, isLoading } = useTravelHubs();

  if (isLoading) {
    return <p className="p-3 text-sm text-muted-foreground">Loading destinations…</p>;
  }

  const filtered = (hubs ?? []).filter(
    (h) => h.is_active && (travelMode === '' || h.travel_modes.includes(travelMode))
  );

  if (filtered.length === 0) {
    return <p className="p-3 text-sm text-muted-foreground">No destinations available.</p>;
  }

  return (
    <div className="space-y-1">
      {filtered.map((hub) => (
        <Card
          key={hub.id}
          className={`cursor-pointer border p-2 text-xs transition-colors hover:bg-accent ${
            selectedHubId === hub.id ? 'border-primary bg-accent' : ''
          }`}
          onClick={() => onSelectHub(hub)}
        >
          <div className="font-medium">{hub.name}</div>
          {hub.description && (
            <div className="text-muted-foreground">{hub.description.slice(0, 80)}</div>
          )}
          <div className="mt-1 text-[10px] text-muted-foreground">
            Modes: {hub.travel_modes.join(', ')}
          </div>
        </Card>
      ))}
    </div>
  );
}

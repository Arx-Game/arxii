/**
 * VoyagePanel — the main voyage panel with four states (#2352).
 *
 * 1. No active voyage: destination picker + method selector + start button
 * 2. DRAFT voyage (leader): party roster, invite, depart, cancel
 * 3. IN_TRANSIT: current hub, legs remaining, advance/complete/abandon
 * 4. DRAFT voyage (invitee): pending invite with accept/decline
 *
 * Renders the VoyageInviteList inbox alongside the panel.
 */

import { useState } from 'react';
import { Ship } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  useTravelMethods,
  useVoyages,
  useStartVoyage,
  useDepartVoyage,
  useAdvanceVoyageLeg,
  useCompleteVoyage,
  useAbandonVoyage,
} from '../queries';
import type { TravelHub } from '../types';
import { HubBrowser } from './HubBrowser';
import { VoyageInviteList } from './VoyageInviteList';

interface VoyagePanelProps {
  characterId: number;
}

export function VoyagePanel({ characterId }: VoyagePanelProps) {
  const { data: methods } = useTravelMethods();
  const { data: voyages } = useVoyages();
  const startVoyage = useStartVoyage(characterId);
  const depart = useDepartVoyage(characterId);
  const advanceLeg = useAdvanceVoyageLeg(characterId);
  const completeVoyage = useCompleteVoyage(characterId);
  const abandonVoyage = useAbandonVoyage(characterId);

  const [selectedHub, setSelectedHub] = useState<TravelHub | null>(null);
  const [selectedMethodId, setSelectedMethodId] = useState<number | null>(null);

  // Find the active voyage (DRAFT or IN_TRANSIT)
  const activeVoyage = (voyages ?? []).find(
    (v) => v.status === 'DRAFT' || v.status === 'IN_TRANSIT'
  );

  if (!characterId) {
    return (
      <div className="flex h-full items-center justify-center p-4">
        <p className="text-sm text-muted-foreground">No active character.</p>
      </div>
    );
  }

  // State 3: IN_TRANSIT
  if (activeVoyage?.status === 'IN_TRANSIT') {
    const totalHubs = activeVoyage.route_hubs.length;
    const currentHub = activeVoyage.current_leg_index + 1;
    return (
      <div className="space-y-3 p-3">
        <VoyageInviteList characterId={characterId} />
        <Card className="border p-3">
          <div className="flex items-center gap-2">
            <Ship className="h-4 w-4" />
            <h3 className="text-sm font-semibold">Voyage to {activeVoyage.destination_name}</h3>
          </div>
          <div className="mt-2 text-xs text-muted-foreground">
            Hub {currentHub}/{totalHubs} · via {activeVoyage.travel_method_name}
          </div>
          {activeVoyage.participants.length > 0 && (
            <div className="mt-2">
              <div className="text-[10px] font-semibold text-muted-foreground">Party</div>
              <div className="text-xs">
                {activeVoyage.participants.map((p) => p.persona_name).join(', ')}
              </div>
            </div>
          )}
          <div className="mt-3 flex flex-wrap gap-2">
            <Button
              size="sm"
              className="h-7 text-xs"
              disabled={advanceLeg.isPending}
              onClick={() => advanceLeg.mutate()}
            >
              Advance
            </Button>
            <Button
              size="sm"
              variant="outline"
              className="h-7 text-xs"
              disabled={completeVoyage.isPending}
              onClick={() => completeVoyage.mutate()}
            >
              Arrive
            </Button>
            <Button
              size="sm"
              variant="ghost"
              className="h-7 text-xs text-destructive"
              disabled={abandonVoyage.isPending}
              onClick={() => abandonVoyage.mutate()}
            >
              Abandon
            </Button>
          </div>
        </Card>
      </div>
    );
  }

  // State 2: DRAFT (leader)
  if (activeVoyage?.status === 'DRAFT') {
    const isLeader = activeVoyage.leader_id === characterId;
    return (
      <div className="space-y-3 p-3">
        <VoyageInviteList characterId={characterId} />
        <Card className="border p-3">
          <div className="flex items-center gap-2">
            <Ship className="h-4 w-4" />
            <h3 className="text-sm font-semibold">
              Draft Voyage to {activeVoyage.destination_name}
            </h3>
          </div>
          <div className="mt-1 text-xs text-muted-foreground">
            via {activeVoyage.travel_method_name}
          </div>
          {activeVoyage.participants.length > 0 && (
            <div className="mt-2">
              <div className="text-[10px] font-semibold text-muted-foreground">Participants</div>
              <div className="text-xs">
                {activeVoyage.participants.map((p) => p.persona_name).join(', ')}
              </div>
            </div>
          )}
          {isLeader && (
            <div className="mt-3 flex flex-wrap gap-2">
              <Button
                size="sm"
                className="h-7 text-xs"
                disabled={depart.isPending}
                onClick={() => depart.mutate()}
              >
                Depart
              </Button>
              <Button
                size="sm"
                variant="ghost"
                className="h-7 text-xs text-destructive"
                disabled={abandonVoyage.isPending}
                onClick={() => abandonVoyage.mutate()}
              >
                Cancel
              </Button>
            </div>
          )}
          {!isLeader && (
            <p className="mt-2 text-xs text-muted-foreground">Waiting for the leader to depart…</p>
          )}
        </Card>
      </div>
    );
  }

  // State 1: No active voyage
  const defaultMethod = (methods ?? []).find((m) => m.is_default);
  const selectedMethod = methods?.find((m) => m.id === selectedMethodId) ?? defaultMethod;
  const travelMode = selectedMethod?.travel_mode ?? '';

  return (
    <div className="space-y-3 p-3">
      <VoyageInviteList characterId={characterId} />
      <Card className="border p-3">
        <div className="flex items-center gap-2">
          <Ship className="h-4 w-4" />
          <h3 className="text-sm font-semibold">Plan a Voyage</h3>
        </div>

        <div className="mt-2">
          <label className="text-[10px] font-semibold text-muted-foreground">Travel Method</label>
          <Select
            value={String(selectedMethod?.id ?? '')}
            onValueChange={(val) => setSelectedMethodId(Number(val))}
          >
            <SelectTrigger className="h-7 text-xs">
              <SelectValue placeholder="Select method…" />
            </SelectTrigger>
            <SelectContent>
              {(methods ?? []).map((m) => (
                <SelectItem key={m.id} value={String(m.id)}>
                  {m.name} ({m.travel_mode})
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="mt-3">
          <label className="text-[10px] font-semibold text-muted-foreground">Destination</label>
          <HubBrowser
            travelMode={travelMode}
            onSelectHub={setSelectedHub}
            selectedHubId={selectedHub?.id}
          />
        </div>

        {selectedHub && selectedMethod && (
          <Button
            size="sm"
            className="mt-3 h-7 w-full text-xs"
            disabled={startVoyage.isPending}
            onClick={() =>
              startVoyage.mutate({
                destination_id: selectedHub.id,
                travel_method_id: selectedMethod.id,
              })
            }
          >
            Start Voyage to {selectedHub.name}
          </Button>
        )}
      </Card>
    </div>
  );
}

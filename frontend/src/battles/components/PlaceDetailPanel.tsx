/**
 * PlaceDetailPanel — the selected battle-map place's roster: units (strength/
 * morale bars, status), player participants (persona name, status), objective
 * holder, and fortifications with integrity. Links out to the bridged combat
 * encounter (world/battles/serializers.py's `encounter_scene_id`, #1236) when
 * one exists.
 */

import { Link } from 'react-router-dom';
import { Shield, ShieldAlert } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';

import type {
  BattlePersonaSummary,
  BattlePlace,
  BattleParticipant,
  BattleSide,
  BattleUnit,
} from '../types';

export interface PlaceDetailPanelProps {
  place: BattlePlace | null;
  sides: BattleSide[];
  units: BattleUnit[];
  participants: BattleParticipant[];
}

/** Both strength and morale run 0..100 (world/battles/constants.py MAX_MORALE; strength starts at its 100 ceiling). */
const MAX_RESOURCE = 100;

function clampResourcePercent(value: number | undefined): number {
  if (value == null) return 0;
  return Math.max(0, Math.min(MAX_RESOURCE, value));
}

function integrityPercent(integrity: number | undefined, maxIntegrity: number | undefined): number {
  if (!integrity || !maxIntegrity) return 0;
  return Math.max(0, Math.min(100, Math.round((integrity / maxIntegrity) * 100)));
}

export function PlaceDetailPanel({ place, sides, units, participants }: PlaceDetailPanelProps) {
  if (!place) {
    return (
      <div
        className="rounded-lg border border-border bg-card p-6 text-center text-sm text-muted-foreground"
        data-testid="battle-place-detail-empty"
      >
        Select a place on the map to see its units and participants.
      </div>
    );
  }

  const placeUnits = units.filter((unit) => unit.place_id === place.id);
  const placeParticipants = participants.filter((participant) => participant.place_id === place.id);
  const holder =
    place.controlled_by_id != null
      ? (sides.find((side) => side.id === place.controlled_by_id) ?? null)
      : null;

  return (
    <div className="flex flex-col gap-4" data-testid="battle-place-detail">
      <div>
        <h3 className="text-sm font-semibold text-foreground">{place.name}</h3>
        <p className="text-xs text-muted-foreground" data-testid="battle-place-objective-holder">
          {holder ? `Held by ${holder.covenant_name ?? holder.role ?? 'a side'}` : 'Uncontrolled'}
        </p>
        {place.encounter_scene_id != null && (
          <Link
            to={`/scenes/${place.encounter_scene_id}/combat`}
            className="text-xs font-medium text-primary underline-offset-2 hover:underline"
            data-testid="battle-place-view-encounter"
          >
            View encounter
          </Link>
        )}
      </div>

      {place.fortifications.length > 0 && (
        <div className="flex flex-col gap-2">
          <h4 className="text-xs font-semibold uppercase text-muted-foreground">Fortifications</h4>
          {place.fortifications.map((fort) => (
            <div
              key={fort.id}
              className="flex items-center gap-2 text-xs"
              data-testid="battle-fortification-row"
            >
              {fort.breached ? (
                <ShieldAlert className="h-4 w-4 shrink-0 text-destructive" />
              ) : (
                <Shield className="h-4 w-4 shrink-0 text-muted-foreground" />
              )}
              <span className="capitalize">{fort.kind}</span>
              <Progress
                value={integrityPercent(fort.integrity, fort.max_integrity)}
                className="h-2 w-24"
              />
              <span className="text-muted-foreground">
                {fort.integrity}/{fort.max_integrity}
              </span>
            </div>
          ))}
        </div>
      )}

      <div className="flex flex-col gap-2">
        <h4 className="text-xs font-semibold uppercase text-muted-foreground">Units</h4>
        {placeUnits.length === 0 ? (
          <p className="text-xs text-muted-foreground">No units at this front.</p>
        ) : (
          placeUnits.map((unit) => (
            <div
              key={unit.id}
              className="rounded-md border border-border p-2"
              data-testid="battle-unit-row"
            >
              <div className="flex items-center justify-between gap-2">
                <span className="truncate text-xs font-medium text-foreground">{unit.name}</span>
                {unit.status && (
                  <Badge variant="outline" className="shrink-0">
                    {unit.status}
                  </Badge>
                )}
              </div>
              <div className="mt-1 flex items-center gap-2">
                <span className="w-14 shrink-0 text-[10px] text-muted-foreground">Strength</span>
                <Progress value={clampResourcePercent(unit.strength)} className="h-1.5 w-full" />
              </div>
              <div className="mt-1 flex items-center gap-2">
                <span className="w-14 shrink-0 text-[10px] text-muted-foreground">Morale</span>
                <Progress value={clampResourcePercent(unit.morale)} className="h-1.5 w-full" />
              </div>
            </div>
          ))
        )}
      </div>

      <div className="flex flex-col gap-2">
        <h4 className="text-xs font-semibold uppercase text-muted-foreground">Participants</h4>
        {placeParticipants.length === 0 ? (
          <p className="text-xs text-muted-foreground">No player characters at this front.</p>
        ) : (
          placeParticipants.map((participant) => {
            const persona = participant.persona as BattlePersonaSummary | null;
            return (
              <div
                key={participant.id}
                className="flex items-center justify-between gap-2 text-xs"
                data-testid="battle-participant-row"
              >
                <span className="truncate">{persona?.name ?? 'Unknown'}</span>
                {participant.status && <Badge variant="outline">{participant.status}</Badge>}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}

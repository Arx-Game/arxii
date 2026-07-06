/**
 * PlaceNode — one front/zone on the battle map canvas (#2009).
 *
 * Read-only: unlike the building builder's RoomNode, this never drags. Ring
 * color shows which side (if any) holds the place as an objective; badges
 * summarize unit/PC presence; a fortification icon flags breached state; a
 * vehicle icon (by vehicle_kind) shows an embedded ship/mount occupying the
 * place (BattleStateCache.vehicle_at_place, #1714).
 */

import { memo } from 'react';
import { Handle, Position } from '@xyflow/react';
import type { Node, NodeProps } from '@xyflow/react';
import { Flame, PawPrint, Plane, Shield, ShieldAlert, Ship, Waves } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

import { Badge } from '@/components/ui/badge';

import type { BattlePlace, BattleVehicleSummary } from '../types';

export type PlaceControlRole = 'attacker' | 'defender' | null;

export interface PlaceNodeData extends Record<string, unknown> {
  place: BattlePlace;
  /** The controlling side's role, resolved from BattlePlace.controlled_by_id. */
  role: PlaceControlRole;
  unitCount: number;
  pcCount: number;
  /** Canvas diameter budget from radiusToPixels(place.footprint_radius, bounds). */
  sizePx: number;
  selected: boolean;
  onSelect: (placeId: number) => void;
}

export type PlaceNodeType = Node<PlaceNodeData>;

const ROLE_RING: Record<'attacker' | 'defender' | 'uncontrolled', string> = {
  attacker: 'border-destructive ring-2 ring-destructive/40',
  defender: 'border-primary ring-2 ring-primary/40',
  uncontrolled: 'border-border',
};

const VEHICLE_ICON: Record<string, LucideIcon> = {
  ship: Ship,
  airship: Plane,
  dragon: Flame,
  kraken: Waves,
  companion: PawPrint,
};

const MIN_SIZE_PX = 96;

function PlaceNodeComponent({ data }: NodeProps<PlaceNodeType>) {
  const { place, role, unitCount, pcCount, selected, sizePx } = data;
  const size = Math.max(MIN_SIZE_PX, Math.round(sizePx * 2));
  const roleKey = role ?? 'uncontrolled';
  const vehicle = place.vehicle as BattleVehicleSummary | null;
  const VehicleIcon = vehicle ? VEHICLE_ICON[vehicle.vehicle_kind] : null;
  const hasFortifications = place.fortifications.length > 0;
  const hasBreach = place.fortifications.some((fort) => fort.breached);

  return (
    <div
      role="button"
      tabIndex={0}
      style={{ width: size, height: size }}
      className={`flex flex-col items-center justify-center gap-1 rounded-full border-2 bg-card p-2 text-center shadow-sm transition-colors hover:border-primary/60 ${ROLE_RING[roleKey]} ${
        selected ? 'ring-4 ring-foreground/30' : ''
      }`}
      onClick={() => data.onSelect(place.id)}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          data.onSelect(place.id);
        }
      }}
      data-testid="battle-place-node"
      data-place-id={place.id}
    >
      <Handle type="target" position={Position.Top} className="!opacity-0" />
      <p className="max-w-full truncate text-xs font-semibold text-foreground">{place.name}</p>
      {place.terrain_type && (
        <Badge variant="outline" className="text-[10px]">
          {place.terrain_type}
        </Badge>
      )}
      <div className="flex flex-wrap items-center justify-center gap-1">
        {unitCount > 0 && (
          <Badge variant="secondary" className="text-[10px]">
            {unitCount} unit{unitCount === 1 ? '' : 's'}
          </Badge>
        )}
        {pcCount > 0 && (
          <Badge variant="secondary" className="text-[10px]">
            {pcCount} PC{pcCount === 1 ? '' : 's'}
          </Badge>
        )}
      </div>
      {(hasFortifications || VehicleIcon) && (
        <div className="flex items-center gap-1 text-muted-foreground">
          {hasFortifications &&
            (hasBreach ? (
              <ShieldAlert
                className="h-4 w-4 text-destructive"
                data-testid="battle-fortification-breached-icon"
              />
            ) : (
              <Shield className="h-4 w-4" data-testid="battle-fortification-intact-icon" />
            ))}
          {VehicleIcon && <VehicleIcon className="h-4 w-4" data-testid="battle-vehicle-icon" />}
        </div>
      )}
      <Handle type="source" position={Position.Bottom} className="!opacity-0" />
    </div>
  );
}

export const PlaceNode = memo(PlaceNodeComponent);

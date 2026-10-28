/**
 * Pressure — rail section showing the viewer's intensity and control on the combat
 * engagement, and what she has surrendered to Fury (#4738).
 *
 * All three figures come from the viewer's own participant row (exact sheet match, as
 * VitalPools finds it): `intensity_modifier`, `control_modifier` and
 * `fury_control_surrendered`. They are null when she has no combat engagement, and the
 * section renders nothing. The Fury chip shows only once she has surrendered control.
 * Anima stays in VitalPools.
 */

import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import type { EncounterDetail } from '../types';
import { findOwnParticipant } from './VitalPools';

export interface PressureProps {
  encounter: EncounterDetail;
  /** The viewer's CharacterSheet PK — identifies their own participant row. */
  characterSheetId: number;
  collapsed?: boolean;
  onToggleCollapse?: () => void;
}

function signed(value: number): string {
  return value > 0 ? `+${value}` : String(value);
}

export function Pressure({
  encounter,
  characterSheetId,
  collapsed = false,
  onToggleCollapse,
}: PressureProps) {
  const own = findOwnParticipant(encounter.participants, characterSheetId);
  const intensity = own?.intensity_modifier ?? null;
  const control = own?.control_modifier ?? null;
  if (intensity === null || control === null) return null;
  const surrendered = own?.fury_control_surrendered ?? 0;

  return (
    <div className="rounded-md border border-border bg-card" data-testid="pressure-section">
      <button
        type="button"
        onClick={onToggleCollapse}
        className="flex w-full items-center justify-between px-3 py-2 text-left"
        aria-expanded={!collapsed}
        data-testid="pressure-toggle"
      >
        <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Pressure
        </span>
        <span
          className={cn(
            'text-muted-foreground transition-transform',
            collapsed ? '-rotate-90' : 'rotate-0'
          )}
          aria-hidden="true"
        >
          ▾
        </span>
      </button>

      {!collapsed && (
        <div className="space-y-2 border-t border-border px-3 py-2 text-sm">
          <div className="flex items-center justify-between" data-testid="pressure-intensity">
            <span className="font-medium">Intensity</span>
            <span className="tabular-nums text-muted-foreground">{signed(intensity)}</span>
          </div>
          <div className="flex items-center justify-between" data-testid="pressure-control">
            <span className="font-medium">Control</span>
            <span className="tabular-nums text-muted-foreground">{signed(control)}</span>
          </div>
          {surrendered > 0 && (
            <Badge
              variant="outline"
              className="border-red-500/60 text-red-300"
              data-testid="pressure-fury-chip"
            >
              Fury: surrendered {surrendered} control
            </Badge>
          )}
        </div>
      )}
    </div>
  );
}

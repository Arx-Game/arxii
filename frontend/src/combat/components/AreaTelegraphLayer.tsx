/**
 * AreaTelegraphLayer — a wound-up attack's covered place, drawn a round ahead (#4676,
 * demo Screen 4): the place tinted fire-orange with a dashed edge and a line saying
 * when it lands. Pointer-transparent, so squares underneath stay clickable.
 */

import { CELL, type MapArea } from '../battleMapLayout';
import { telegraphLine } from '../dodging';
import { LabelChip } from './battleMapPieces';

export interface AreaTelegraph {
  id: number;
  positionId: number;
  attackName: string;
  roundsUntilLanding: number;
}

const FIRE = '#ff7b4a';

export function AreaTelegraphLayer({
  areas,
  telegraphs,
}: {
  areas: Map<number, MapArea>;
  telegraphs: readonly AreaTelegraph[];
}) {
  return (
    <g pointerEvents="none" data-testid="area-telegraphs">
      {telegraphs.map((telegraph) => {
        const area = areas.get(telegraph.positionId);
        if (!area) return null;
        return (
          <g key={telegraph.id} data-testid={`area-telegraph-${telegraph.positionId}`}>
            <rect
              x={area.x * CELL}
              y={area.y * CELL}
              width={area.w * CELL}
              height={area.h * CELL}
              fill="#ff5a2a"
              fillOpacity={0.22}
              stroke={FIRE}
              strokeWidth={3}
              strokeDasharray="8 5"
            />
            <LabelChip
              x={area.x * CELL + 6}
              y={(area.y + area.h) * CELL - 10}
              text={telegraphLine(telegraph.attackName, telegraph.roundsUntilLanding)}
              color="#ffb08a"
            />
          </g>
        );
      })}
    </g>
  );
}

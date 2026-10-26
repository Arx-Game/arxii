/**
 * The battle map's feature layer (#4675, slice 3 of #4651): each feature standing in a
 * place (a chandelier, a rope) drawn on its square, below the tokens.
 *
 * A feature with art shows that art clipped to its one square; one without shows a
 * neutral ring with its name's initial. A feature with no square, or a square outside
 * its place's area (the area was shrunk after it was placed), sits on the area's top
 * row from the right. Drawing only: pointer events are off, so the squares under a
 * feature stay clickable, and a stunt is picked from the move panel, never here.
 */

import type { PositionNodeLike } from '@/areas/components/TacticalMap';
import { CELL } from '../battleMapLayout';
import type { MapArea, Square } from '../battleMapLayout';
import { DISPLAY_FONT, LABEL_BG } from '../battleMapPalette';

const FEATURE_RING = '#c9a04a';
const FEATURE_TEXT = '#ffe08a';

type MapFeature = PositionNodeLike['features'][number];

interface PlacedFeature {
  feature: MapFeature;
  square: Square;
}

function inside(area: MapArea, x: number, y: number): boolean {
  return x >= area.x && x < area.x + area.w && y >= area.y && y < area.y + area.h;
}

/** Where each of a place's features is drawn. */
function featureSquares(area: MapArea, features: readonly MapFeature[]): PlacedFeature[] {
  let corner = 0;
  return features.map((feature) => {
    const { square_x: x, square_y: y } = feature;
    if (x !== null && y !== null && inside(area, x, y)) return { feature, square: { x, y } };
    // The top row from the right; a full row stacks on its leftmost square.
    const col = Math.max(area.w - 1 - corner, 0);
    corner += 1;
    return { feature, square: { x: area.x + col, y: area.y } };
  });
}

function FeatureMark({ placed, clipId }: { placed: PlacedFeature; clipId: string }) {
  const { feature, square } = placed;
  const x = square.x * CELL;
  const y = square.y * CELL;
  const cx = x + CELL / 2;
  const cy = y + CELL / 2;
  return (
    <g
      data-testid={`battle-map-feature-${feature.id}`}
      data-square={`${square.x},${square.y}`}
      data-art={feature.art_url ? 'true' : undefined}
    >
      <title>{feature.name}</title>
      {feature.art_url ? (
        <>
          <defs>
            <clipPath id={clipId}>
              <rect x={x} y={y} width={CELL} height={CELL} />
            </clipPath>
          </defs>
          <image
            href={feature.art_url}
            x={x}
            y={y}
            width={CELL}
            height={CELL}
            preserveAspectRatio="xMidYMid slice"
            clipPath={`url(#${clipId})`}
          />
        </>
      ) : (
        <>
          <circle
            cx={cx}
            cy={cy}
            r={CELL * 0.36}
            fill={LABEL_BG}
            fillOpacity={0.7}
            stroke={FEATURE_RING}
            strokeWidth={2}
          />
          <text
            x={cx}
            y={cy + 5}
            textAnchor="middle"
            fontFamily={DISPLAY_FONT}
            fontSize={14}
            fill={FEATURE_TEXT}
          >
            {feature.name.charAt(0).toUpperCase()}
          </text>
        </>
      )}
    </g>
  );
}

export function BattleMapFeatures({
  nodes,
  areas,
  uid,
}: {
  nodes: PositionNodeLike[];
  areas: Map<number, MapArea>;
  uid: string;
}) {
  const marks = nodes.flatMap((node) => {
    // An aerial place has no area of its own; its features stand over its anchor's.
    const area =
      areas.get(node.id) ??
      (node.elevation_anchor_id !== null ? areas.get(node.elevation_anchor_id) : undefined);
    if (!area) return [];
    return featureSquares(area, node.features ?? []);
  });
  if (marks.length === 0) return null;
  return (
    <g data-testid="battle-map-features" pointerEvents="none">
      {marks.map((placed) => (
        <FeatureMark
          key={placed.feature.id}
          placed={placed}
          clipId={`${uid}-feature-${placed.feature.id}`}
        />
      ))}
    </g>
  );
}

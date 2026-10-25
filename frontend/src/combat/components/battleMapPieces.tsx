/**
 * Drawing pieces of the battle map (#4670): label chips, route labels, cover badges,
 * mark glyphs and portrait tokens. Pure SVG renderers; BattleMap owns the clicks.
 */

import type { MouseEvent, ReactNode } from 'react';
import { EyeOff, House, Shield, ShieldCheck, ShieldPlus, Swords } from 'lucide-react';

import type { PositionNodeLike } from '@/areas/components/TacticalMap';
import type { OccupantMarkKind } from '@/areas/components/PositionMapNode';
import {
  AIR,
  AIR_LIFT,
  DISPLAY_FONT,
  GOLD,
  LABEL_BG,
  LABEL_TEXT,
  SIDE_RING,
  TAG_FONT,
  TOKEN_R,
  chipWidth,
} from '../battleMapPalette';
import type { BattleOccupant } from '../battleMapPalette';

const MARK_STYLE: Record<OccupantMarkKind, { icon: typeof Swords; fill: string }> = {
  locked: { icon: Swords, fill: '#e11d48' },
  covering: { icon: ShieldPlus, fill: '#0284c7' },
  covered: { icon: ShieldCheck, fill: '#0284c7' },
};

function colorForName(name: string): string {
  let hash = 0;
  for (let i = 0; i < name.length; i++) hash = Math.trunc(hash * 31 + name.charCodeAt(i));
  return `hsl(${Math.abs(hash) % 360}, 55%, 35%)`;
}

/** A dark chip with the place's name, at a point in viewBox units. */
export function LabelChip({
  x,
  y,
  text,
  color,
  badges,
  anchor = 'start',
}: {
  x: number;
  y: number;
  text: string;
  color: string;
  badges?: ReactNode;
  anchor?: 'start' | 'end';
}) {
  const width = chipWidth(text);
  const left = anchor === 'end' ? x - width : x;
  return (
    <g pointerEvents="none">
      <rect
        x={left - 3}
        y={y - 11}
        width={width}
        height={15}
        rx={3}
        fill={LABEL_BG}
        fillOpacity={0.75}
      />
      <text x={left} y={y} fontFamily={DISPLAY_FONT} fontSize={11} letterSpacing={0.5} fill={color}>
        {text}
      </text>
      {badges && (
        <g transform={`translate(${left + width - 1}, ${y - 11})`} pointerEvents="auto">
          {badges}
        </g>
      )}
    </g>
  );
}

/** A route's gate or wall text, centred on the route's midpoint. */
export function RouteLabel({
  x,
  y,
  text,
  color,
  testId,
}: {
  x: number;
  y: number;
  text: string;
  color: string;
  testId: string;
}) {
  const width = text.length * 5.6 + 10;
  return (
    <g data-testid={testId} pointerEvents="none">
      <rect
        x={x - width / 2}
        y={y - 8}
        width={width}
        height={14}
        rx={3}
        fill={LABEL_BG}
        fillOpacity={0.85}
      />
      <text x={x} y={y + 3} textAnchor="middle" fontFamily={TAG_FONT} fontSize={9} fill={color}>
        {text}
      </text>
    </g>
  );
}

export function CoverBadges({ node }: { node: PositionNodeLike }) {
  if (!node.is_roofed && !node.screens_ranged) return null;
  return (
    <>
      {node.is_roofed && (
        <g data-testid="position-roof-badge" aria-label="Roofed">
          <title>Roofed</title>
          <rect width={15} height={15} rx={3} fill={LABEL_BG} fillOpacity={0.75} />
          <House x={2} y={2} width={11} height={11} color="#fcd34d" aria-hidden="true" />
        </g>
      )}
      {node.screens_ranged && (
        <g
          data-testid="position-screen-badge"
          aria-label="Screened"
          transform={`translate(${node.is_roofed ? 17 : 0}, 0)`}
        >
          <title>Screened</title>
          <rect width={15} height={15} rx={3} fill={LABEL_BG} fillOpacity={0.75} />
          <EyeOff x={2} y={2} width={11} height={11} color="#7dd3fc" aria-hidden="true" />
        </g>
      )}
    </>
  );
}

export function MarkGlyph({
  kind,
  title,
  cx,
  cy,
  icon: Icon,
  fill,
  testId,
}: {
  kind: string;
  title: string;
  cx: number;
  cy: number;
  icon: typeof Swords;
  fill: string;
  testId: string;
}) {
  return (
    <g data-testid={testId} data-mark={kind} aria-label={title} role="img" pointerEvents="auto">
      <title>{title}</title>
      <circle cx={cx} cy={cy} r={6} fill={fill} stroke={LABEL_BG} strokeWidth={1} />
      <Icon x={cx - 4} y={cy - 4} width={8} height={8} color="#fff" aria-hidden="true" />
    </g>
  );
}

export function Token({
  occupant,
  cx,
  cy,
  clipId,
  aerial,
  rampartElement,
  onClick,
}: {
  occupant: BattleOccupant;
  cx: number;
  cy: number;
  clipId: string;
  aerial: boolean;
  rampartElement: string | null;
  /** The same as a click on the square (or the air) the token stands on. */
  onClick: () => void;
}) {
  const url = occupant.thumbnailMediaUrl ?? occupant.thumbnailUrl ?? null;
  const ring = aerial ? AIR : SIDE_RING[occupant.side];
  const bystander = occupant.side === 'bystander';
  const tagWidth = occupant.name.length * 5.4 + 8;
  const title = bystander ? `${occupant.name} (bystander)` : occupant.name;
  const handleClick = (event: MouseEvent) => {
    event.stopPropagation();
    onClick();
  };
  return (
    <g
      data-testid="occupant-token"
      data-side={occupant.side}
      data-bystander={bystander ? 'true' : undefined}
      data-viewer={occupant.isViewer ? 'true' : undefined}
      data-aerial={aerial ? 'true' : undefined}
      opacity={bystander ? 0.45 : 1}
      pointerEvents="auto"
      onClick={handleClick}
    >
      <title>{title}</title>
      <defs>
        <clipPath id={clipId}>
          <circle cx={cx} cy={cy} r={TOKEN_R} />
        </clipPath>
      </defs>
      {occupant.isViewer && (
        <circle
          data-testid="viewer-halo"
          cx={cx}
          cy={cy}
          r={TOKEN_R + 6}
          fill="none"
          stroke={GOLD}
          strokeWidth={2}
          strokeDasharray="3 3"
        />
      )}
      <circle
        cx={cx}
        cy={cy + (aerial ? AIR_LIFT + 4 : 2)}
        r={TOKEN_R + 1}
        fill="#000"
        opacity={aerial ? 0.3 : 0.5}
      />
      <circle cx={cx} cy={cy} r={TOKEN_R} fill={colorForName(occupant.name)} />
      {url ? (
        <image
          href={url}
          x={cx - TOKEN_R}
          y={cy - TOKEN_R}
          width={TOKEN_R * 2}
          height={TOKEN_R * 2}
          preserveAspectRatio="xMidYMid slice"
          clipPath={`url(#${clipId})`}
          role="img"
          aria-label={occupant.name}
        />
      ) : (
        <text
          x={cx}
          y={cy + 5}
          textAnchor="middle"
          fontSize={14}
          fontWeight={600}
          fill="#fff"
          aria-hidden="true"
        >
          {(occupant.name.trim()[0] ?? '?').toUpperCase()}
        </text>
      )}
      <circle cx={cx} cy={cy} r={TOKEN_R} fill="none" stroke={ring} strokeWidth={2.5} />
      {rampartElement != null && (
        <MarkGlyph
          kind="cover"
          testId="occupant-mark-cover"
          title={`${occupant.name}: behind ${rampartElement} rampart`}
          cx={cx - TOKEN_R + 2}
          cy={cy + TOKEN_R - 2}
          icon={Shield}
          fill="#047857"
        />
      )}
      {(occupant.marks ?? []).map((mark) => (
        <MarkGlyph
          key={mark.kind}
          kind={mark.kind}
          testId={`occupant-mark-${mark.kind}`}
          title={mark.title}
          cx={cx + TOKEN_R - 2}
          cy={mark.kind === 'locked' ? cy - TOKEN_R + 2 : cy + TOKEN_R - 2}
          icon={MARK_STYLE[mark.kind].icon}
          fill={MARK_STYLE[mark.kind].fill}
        />
      ))}
      <rect
        x={cx - tagWidth / 2}
        y={cy + TOKEN_R + 1}
        width={tagWidth}
        height={11}
        rx={3}
        fill={LABEL_BG}
        fillOpacity={0.8}
      />
      <text
        x={cx}
        y={cy + TOKEN_R + 9.5}
        textAnchor="middle"
        fontFamily={TAG_FONT}
        fontSize={8.5}
        fill={LABEL_TEXT}
      >
        {occupant.name}
      </text>
    </g>
  );
}

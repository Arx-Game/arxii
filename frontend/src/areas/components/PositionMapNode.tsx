/**
 * Custom React Flow node for the tactical map (#2006) — one position, with
 * occupant avatars and kind-based styling. Read-only: no drag, no resize.
 */

import { memo } from 'react';
import { Handle, Position as FlowPosition } from '@xyflow/react';
import type { Node, NodeProps } from '@xyflow/react';

import { Shield, ShieldCheck, ShieldPlus, Swords } from 'lucide-react';

import { PersonaAvatar } from '@/components/PersonaAvatar';
import type { PersonaAvatarSource } from '@/components/PersonaAvatar';

/**
 * Tactical status the map draws on one occupant's avatar (#3555). The
 * encounter already knows these; the caller (CombatTacticalMap) resolves the
 * names into a ready-to-show `title` so this node stays a pure renderer.
 *
 * - `locked`: an active engagement lock (foil duel) with the named combatant.
 * - `covering`: this occupant declared the cover maneuver for the named ally.
 * - `covered`: the named ally is covering this occupant this round.
 *
 * Behind-rampart cover is not a mark: it is derived here from the node's own
 * rampart fields, since every occupant of a covered position is behind it.
 */
export type OccupantMarkKind = 'locked' | 'covering' | 'covered';

export interface OccupantMark {
  kind: OccupantMarkKind;
  title: string;
}

export interface OccupantSummary extends PersonaAvatarSource {
  marks?: OccupantMark[];
}

const MARK_STYLES: Record<OccupantMarkKind, { icon: typeof Swords; className: string }> = {
  locked: { icon: Swords, className: '-right-1 -top-1 bg-rose-600 text-white' },
  covering: { icon: ShieldPlus, className: '-bottom-1 -right-1 bg-sky-600 text-white' },
  covered: { icon: ShieldCheck, className: '-bottom-1 -right-1 bg-sky-600 text-white' },
};

const KIND_STYLES: Record<string, string> = {
  primary: 'border-border bg-card',
  feature: 'border-border bg-card',
  elevated: 'border-sky-500/60 bg-sky-950/20',
  aerial: 'border-cyan-400/60 bg-cyan-950/20',
  chasm: 'border-red-800/60 bg-red-950/30',
  barrier_side: 'border-border bg-card',
};

// Rampart element -> ring border color (#2209). Keyed lowercase;
// unrecognized elements fall back to a neutral ring so a new element never
// renders invisibly.
const RAMPART_ELEMENT_RING: Record<string, string> = {
  stone: 'border-slate-400',
  wind: 'border-sky-400',
  fire: 'border-orange-400',
  thorn: 'border-green-400',
};
const RAMPART_ELEMENT_RING_FALLBACK = 'border-zinc-400';

export interface PositionMapNodeData extends Record<string, unknown> {
  positionId: number;
  name: string;
  kind: string;
  occupants: OccupantSummary[];
  canMoveHere: boolean;
  onClick: (positionId: number) => void;
  rampartElement: string | null;
  rampartIntegrity: number | null;
  rampartMaxIntegrity: number | null;
  rampartCrackState: string | null;
}

/**
 * Tailwind classes + a11y title for a covered position's rampart ring
 * (#2209). Solid ring when intact, dashed when cracked, faint/pulsing
 * dashed when crumbling. Returns null when the position carries no rampart.
 */
function rampartRingProps(data: PositionMapNodeData): { className: string; title: string } | null {
  if (data.rampartElement == null) return null;

  const colorClass =
    RAMPART_ELEMENT_RING[data.rampartElement.toLowerCase()] ?? RAMPART_ELEMENT_RING_FALLBACK;

  let stateClass: string;
  switch (data.rampartCrackState) {
    case 'cracked':
      stateClass = 'border-2 border-dashed';
      break;
    case 'crumbling':
      stateClass = 'border border-dashed opacity-50 animate-pulse';
      break;
    default:
      stateClass = 'border-2 border-solid';
  }

  return {
    className: `pointer-events-none absolute -inset-1 rounded-lg ${colorClass} ${stateClass}`,
    title: `${data.rampartElement} Rampart ${data.rampartIntegrity ?? '?'}/${data.rampartMaxIntegrity ?? '?'}`,
  };
}

export type PositionMapNodeType = Node<PositionMapNodeData>;

function OccupantMarkGlyph({ kind, title }: OccupantMark) {
  const { icon: Icon, className } = MARK_STYLES[kind];
  return (
    <span
      className={`absolute flex h-3.5 w-3.5 items-center justify-center rounded-full ring-1 ring-background ${className}`}
      title={title}
      aria-label={title}
      data-testid={`occupant-mark-${kind}`}
    >
      <Icon className="h-2.5 w-2.5" aria-hidden="true" />
    </span>
  );
}

/**
 * One occupant avatar plus its status glyphs (#3555): the caller-supplied
 * marks, and a behind-cover glyph whenever the node itself carries a rampart
 * (a Rampart is deleted at zero integrity, so "present" means "still cover").
 */
function OccupantAvatar({
  occupant,
  rampartElement,
}: {
  occupant: OccupantSummary;
  rampartElement: string | null;
}) {
  return (
    <span className="relative inline-flex" data-testid="occupant-avatar">
      <PersonaAvatar source={occupant} size="sm" />
      {rampartElement != null && (
        <span
          className="absolute -bottom-1 -left-1 flex h-3.5 w-3.5 items-center justify-center rounded-full bg-emerald-700 text-white ring-1 ring-background"
          title={`${occupant.name}: behind ${rampartElement} rampart`}
          aria-label={`${occupant.name}: behind ${rampartElement} rampart`}
          data-testid="occupant-mark-cover"
        >
          <Shield className="h-2.5 w-2.5" aria-hidden="true" />
        </span>
      )}
      {(occupant.marks ?? []).map((mark) => (
        <OccupantMarkGlyph key={mark.kind} {...mark} />
      ))}
    </span>
  );
}

function PositionMapNodeComponent({ data }: NodeProps<PositionMapNodeType>) {
  const kindClass = KIND_STYLES[data.kind] ?? KIND_STYLES.feature;
  const rampartRing = rampartRingProps(data);
  return (
    <button
      type="button"
      className={`relative w-[140px] cursor-pointer rounded-md border p-2 text-left shadow-sm transition-colors hover:border-primary/60 ${kindClass} ${
        data.canMoveHere ? 'ring-2 ring-amber-400/50' : ''
      }`}
      onClick={() => data.onClick(data.positionId)}
      // React Flow sets `pointer-events: none` inline on the `.react-flow__node`
      // wrapper for nodes that are neither selectable nor draggable (both true
      // here — this is a read-only map) and that have no `onNodeClick` wired at
      // the <ReactFlow> level. That inherits down to this div and would silently
      // swallow clicks, so it's overridden explicitly here.
      style={{ pointerEvents: 'auto' }}
      data-testid={`tactical-map-node-${data.positionId}`}
      data-position-id={data.positionId}
      data-position-kind={data.kind}
      data-rampart-crack-state={data.rampartCrackState ?? undefined}
      title={rampartRing?.title}
    >
      {rampartRing && (
        <div className={rampartRing.className} data-testid="rampart-ring" aria-hidden="true" />
      )}
      <Handle type="target" position={FlowPosition.Top} className="!opacity-0" />
      <p className="truncate text-xs font-semibold text-foreground">{data.name}</p>
      {data.occupants.length > 0 && (
        <div className="mt-1 flex flex-wrap gap-1.5">
          {data.occupants.map((occupant, index) => (
            <OccupantAvatar
              key={`${occupant.name}-${index}`}
              occupant={occupant}
              rampartElement={data.rampartElement}
            />
          ))}
        </div>
      )}
      <Handle type="source" position={FlowPosition.Bottom} className="!opacity-0" />
    </button>
  );
}

export const PositionMapNode = memo(PositionMapNodeComponent);

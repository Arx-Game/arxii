/**
 * Custom React Flow node for the tactical map (#2006) — one position, with
 * occupant avatars and kind-based styling. Read-only: no drag, no resize.
 */

import { memo } from 'react';
import { Handle, Position as FlowPosition } from '@xyflow/react';
import type { Node, NodeProps } from '@xyflow/react';

import { PersonaAvatar } from '@/components/PersonaAvatar';
import type { PersonaAvatarSource } from '@/components/PersonaAvatar';

export type OccupantSummary = PersonaAvatarSource;

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

function PositionMapNodeComponent({ data }: NodeProps<PositionMapNodeType>) {
  const kindClass = KIND_STYLES[data.kind] ?? KIND_STYLES.feature;
  const rampartRing = rampartRingProps(data);
  return (
    <div
      role="button"
      tabIndex={0}
      className={`relative w-[140px] cursor-pointer rounded-md border p-2 shadow-sm transition-colors hover:border-primary/60 ${kindClass} ${
        data.canMoveHere ? 'ring-2 ring-amber-400/50' : ''
      }`}
      onClick={() => data.onClick(data.positionId)}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          data.onClick(data.positionId);
        }
      }}
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
        <div className="mt-1 flex flex-wrap gap-1">
          {data.occupants.map((occupant, index) => (
            <PersonaAvatar key={`${occupant.name}-${index}`} source={occupant} size="sm" />
          ))}
        </div>
      )}
      <Handle type="source" position={FlowPosition.Bottom} className="!opacity-0" />
    </div>
  );
}

export const PositionMapNode = memo(PositionMapNodeComponent);

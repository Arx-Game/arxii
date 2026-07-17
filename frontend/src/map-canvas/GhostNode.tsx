/**
 * GhostNode — a custom React Flow node for an empty cell adjacent to a
 * placed room; clicking it starts a dig. Shared by the building builder
 * canvas (#670) and the staff world-builder canvas (#2449) — moved here
 * from `@/buildings/components/RoomNode` alongside `ghostCells` (fix pass,
 * task-6 report).
 *
 * The tooltip label is caller-supplied rather than computed from
 * `ghost.direction` here: buildings' `BuilderCanvas` passes a
 * direction-relative label ("Dig north"), while the world-builder canvas's
 * absolute-grid-cell rooms have no dig-direction concept and pass a
 * cell-based label ("Dig room here") instead.
 */

import { memo } from 'react';
import type { Node, NodeProps } from '@xyflow/react';

import type { GhostCell } from './ghosts';

export interface GhostNodeData extends Record<string, unknown> {
  ghost: GhostCell;
  onDig: (ghost: GhostCell) => void;
  /** Hover tooltip text — direction-based for buildings, cell-based for world-builder. */
  label: string;
}

export type GhostNodeType = Node<GhostNodeData>;

function GhostNodeComponent({ data }: NodeProps<GhostNodeType>) {
  return (
    <button
      type="button"
      className="flex h-[104px] w-[104px] items-center justify-center rounded-md border border-dashed border-muted-foreground/30 bg-muted/20 text-2xl text-muted-foreground/50 transition-colors hover:border-primary/60 hover:text-primary"
      onClick={() => data.onDig(data.ghost)}
      title={data.label}
      data-testid="builder-ghost-node"
    >
      +
    </button>
  );
}

export const GhostNode = memo(GhostNodeComponent);

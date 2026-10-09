/**
 * KinTreeGraph — the family as a generation-layered graph (#2062, #3003).
 *
 * ADR-0097 is binding here: this is NOT a binary mother/father tree. N-parent
 * fan-in is real (Tree-of-Souls polycules, a vampiric progenitor edge
 * coexisting with biological parents), so a node's generation is derived by
 * walking parentage depth from the roots and every visible parentage edge is
 * drawn individually rather than merged into a two-slot layout. The truth
 * layer telnet can't show rides the edges too: a secret-known edge is dashed
 * (`data-via-secret="true"`), and a believed-but-false edge is marked
 * (`data-believed-false="true"`) and rendered at reduced opacity. `kind` (blood
 * vs marriage vs foster) is color-coded so the three never read as ambiguous;
 * unions are a separate edge type, drawn as a connector between members.
 *
 * A node prints its tree form (`short_name`: the first name for a person of this
 * family, the birth family added for someone taken in, first + own family for a
 * relative not of the name) and nothing else (#4209): no definition tier, since
 * the only distinction a reader needs is whether the person is played, and a
 * played person's name is a link to their sheet. Clicking the box still selects.
 */
import { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';

import { cn } from '@/lib/utils';
import { urls } from '@/utils/urls';

import { computeGenerations } from '../generations';
import type { KinspersonNode, ParentageEdge, UnionEdge } from '../types';

interface Props {
  nodes: KinspersonNode[];
  parentage: ParentageEdge[];
  unions: UnionEdge[];
  selectedNodeId: number | null;
  onSelectNode: (node: KinspersonNode) => void;
}

interface Point {
  x: number;
  y: number;
}

const NODE_W = 152;
const NODE_H = 56;
const COL_GAP = 24;
const ROW_H = 128;
const PADDING = 28;

function layoutNodes(
  nodes: KinspersonNode[],
  generation: Map<number, number>
): { positions: Map<number, Point>; width: number; height: number } {
  const byGeneration = new Map<number, KinspersonNode[]>();
  for (const node of nodes) {
    const gen = generation.get(node.id) ?? 0;
    const row = byGeneration.get(gen) ?? [];
    row.push(node);
    byGeneration.set(gen, row);
  }

  const positions = new Map<number, Point>();
  let maxRowWidth = 0;
  const sortedGens = [...byGeneration.keys()].sort((a, b) => a - b);
  for (const gen of sortedGens) {
    const row = byGeneration.get(gen) ?? [];
    row.forEach((node, idx) => {
      positions.set(node.id, {
        x: PADDING + idx * (NODE_W + COL_GAP) + NODE_W / 2,
        y: PADDING + gen * ROW_H + NODE_H / 2,
      });
    });
    maxRowWidth = Math.max(maxRowWidth, row.length * (NODE_W + COL_GAP) - COL_GAP);
  }

  const maxGen = sortedGens.length > 0 ? sortedGens[sortedGens.length - 1] : 0;
  return {
    positions,
    width: Math.max(maxRowWidth, NODE_W) + PADDING * 2,
    height: PADDING * 2 + (maxGen + 1) * ROW_H,
  };
}

// A categorical color per parentage kind, reusing the theme's chart palette
// (already tuned for both themes) rather than inventing raw hex values.
// Biological is the plain/neutral case; every other kind gets its own color
// so blood vs marriage vs foster never reads as ambiguous.
const KIND_STROKE_CLASS: Record<string, string> = {
  biological: 'stroke-foreground',
  tree_of_souls: 'stroke-chart-1',
  vampiric_embrace: 'stroke-chart-2',
  adoptive: 'stroke-chart-3',
  foster: 'stroke-chart-4',
  acknowledged: 'stroke-chart-5',
};

function kindStrokeClass(kind: string): string {
  return KIND_STROKE_CLASS[kind] ?? 'stroke-muted-foreground';
}

export function KinTreeGraph({ nodes, parentage, unions, selectedNodeId, onSelectNode }: Props) {
  const navigate = useNavigate();
  const generation = useMemo(() => computeGenerations(nodes, parentage), [nodes, parentage]);
  const { positions, width, height } = useMemo(
    () => layoutNodes(nodes, generation),
    [nodes, generation]
  );

  return (
    <svg
      role="img"
      aria-label="Kin tree"
      viewBox={`0 0 ${width} ${height}`}
      className="h-auto w-full"
      style={{ minWidth: width }}
    >
      {/* Parentage edges first so nodes draw on top of them. */}
      <g>
        {parentage.map((edge, idx) => {
          const parentPos = positions.get(edge.parent_id);
          const childPos = positions.get(edge.child_id);
          if (!parentPos || !childPos) return null;
          const believedFalse = edge.is_true === false;
          return (
            <line
              key={`parentage-${edge.parent_id}-${edge.child_id}-${edge.kind}-${idx}`}
              x1={parentPos.x}
              y1={parentPos.y}
              x2={childPos.x}
              y2={childPos.y}
              strokeWidth={2}
              strokeDasharray={edge.via_secret ? '5 4' : undefined}
              className={cn(kindStrokeClass(edge.kind), believedFalse && 'opacity-40')}
              data-kind={edge.kind}
              {...(edge.via_secret ? { 'data-via-secret': 'true' } : {})}
              {...(believedFalse ? { 'data-believed-false': 'true' } : {})}
            />
          );
        })}
      </g>

      {/* Union connectors — a separate edge type from parentage. */}
      <g>
        {unions.flatMap((union) => {
          const memberPositions = union.member_ids
            .map((id) => positions.get(id))
            .filter((p): p is Point => p != null);
          if (memberPositions.length < 2) return [];
          return memberPositions
            .slice(1)
            .map((pos, idx) => (
              <line
                key={`union-${union.id}-${idx}`}
                x1={memberPositions[idx].x}
                y1={memberPositions[idx].y}
                x2={pos.x}
                y2={pos.y}
                strokeWidth={2}
                strokeDasharray={union.ended ? '2 3' : undefined}
                className={cn('stroke-primary', union.ended && 'opacity-40')}
                data-union-kind={union.kind}
                {...(union.ended ? { 'data-union-ended': 'true' } : {})}
              />
            ));
        })}
      </g>

      {/* Nodes. */}
      <g>
        {nodes.map((node) => {
          const pos = positions.get(node.id);
          if (!pos) return null;
          const isSelected = node.id === selectedNodeId;
          const label = `${node.short_name}${node.is_deceased ? ' †' : ''}`;
          const sheetUrl =
            node.roster_entry_id != null ? urls.character(node.roster_entry_id) : null;
          return (
            <g
              key={node.id}
              data-testid="kin-node"
              data-node-id={node.id}
              role="button"
              tabIndex={0}
              className="cursor-pointer outline-none"
              onClick={() => onSelectNode(node)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') onSelectNode(node);
              }}
            >
              <rect
                x={pos.x - NODE_W / 2}
                y={pos.y - NODE_H / 2}
                width={NODE_W}
                height={NODE_H}
                rx={8}
                ry={8}
                strokeWidth={2}
                className={cn(
                  isSelected ? 'fill-primary/10 stroke-primary' : 'fill-card stroke-border',
                  node.is_deceased && 'opacity-60'
                )}
              />
              {sheetUrl ? (
                // A played person's name is the link to their sheet; the box
                // around it still selects. An SVG anchor, navigated in-app.
                <a
                  href={sheetUrl}
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    navigate(sheetUrl);
                  }}
                >
                  <text
                    x={pos.x}
                    y={pos.y + 5}
                    textAnchor="middle"
                    className="select-none fill-primary text-sm font-medium underline"
                  >
                    {label}
                  </text>
                </a>
              ) : (
                <text
                  x={pos.x}
                  y={pos.y + 5}
                  textAnchor="middle"
                  className="select-none fill-foreground text-sm font-medium"
                >
                  {label}
                </text>
              )}
            </g>
          );
        })}
      </g>
    </svg>
  );
}

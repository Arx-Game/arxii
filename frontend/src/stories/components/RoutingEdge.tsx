/**
 * RoutingEdge (#3563): a bezier edge whose label is an HTML element, so the
 * full rule text can ride a native title tooltip. React Flow's default edge
 * label is SVG text and cannot carry one.
 */
import { BaseEdge, EdgeLabelRenderer, getBezierPath } from '@xyflow/react';
import type { Edge, EdgeProps } from '@xyflow/react';

export interface RoutingEdgeData extends Record<string, unknown> {
  /** Visible label, truncated. */
  label: string;
  /** Untruncated text shown on hover. */
  fullLabel: string;
}

export type RoutingEdgeType = Edge<RoutingEdgeData, 'routingEdge'>;

export function RoutingEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  style,
  markerEnd,
  data,
}: EdgeProps<RoutingEdgeType>) {
  const [path, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });
  return (
    <>
      <BaseEdge id={id} path={path} style={style} markerEnd={markerEnd} />
      {data?.label ? (
        <EdgeLabelRenderer>
          <div
            className="nodrag nopan pointer-events-auto absolute rounded bg-background/85 px-1 text-[10px] text-muted-foreground"
            style={{ transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)` }}
            title={data.fullLabel}
            data-testid="dag-edge-label"
          >
            {data.label}
          </div>
        </EdgeLabelRenderer>
      ) : null}
    </>
  );
}

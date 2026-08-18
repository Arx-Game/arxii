/**
 * AreaArrangeCanvas — the city map of wards (#3269 Phase C): the selected
 * area's child areas on the same drag-to-place grid the room canvas uses,
 * one level up. Dragging a child to a cell dispatches `edit_area` with the
 * parent-local `grid_x`/`grid_y` (cosmetic hint data, never routing).
 * Children without coordinates park in the standard tray column.
 */
import { useCallback } from 'react';
import { Handle, Position } from '@xyflow/react';

import { CELL } from '@/map-canvas/coords';
import { MapCanvasShell } from '@/map-canvas/MapCanvasShell';
import { useGridCanvasNodes, type PlaceRoomArgs } from '@/map-canvas/useGridCanvasNodes';

import type { WorldBuilderArea } from '../types';

function AreaNode({ data }: { data: { area: WorldBuilderArea; selected: boolean } }) {
  return (
    <div
      className={`rounded border bg-card px-2 py-1 text-xs shadow ${
        data.selected ? 'ring-2 ring-primary' : ''
      }`}
      style={{ width: CELL - 16 }}
      data-testid={`area-node-${data.area.id}`}
    >
      <Handle type="target" position={Position.Top} style={{ visibility: 'hidden' }} />
      <p className="truncate font-medium">{data.area.name}</p>
      <p className="text-muted-foreground">{data.area.level_display}</p>
      <Handle type="source" position={Position.Bottom} style={{ visibility: 'hidden' }} />
    </div>
  );
}

const nodeTypes = { room: AreaNode };

export interface AreaArrangeCanvasProps {
  childAreas: WorldBuilderArea[];
  selectedAreaId: number | null;
  onSelectArea: (areaId: number) => void;
  runAction: (key: string, kwargs: Record<string, unknown>) => void;
}

export function AreaArrangeCanvas({
  childAreas,
  selectedAreaId,
  onSelectArea,
  runAction,
}: AreaArrangeCanvasProps) {
  const rows = childAreas.map((area) => ({
    ...area,
    floor: 0,
  }));

  const onPlaceRoom = useCallback(
    ({ roomId, grid_x, grid_y }: PlaceRoomArgs) => {
      runAction('edit_area', { area_id: roomId, grid_x, grid_y });
    },
    [runAction]
  );

  const { nodes, edges, onNodesChange, onNodeDragStop } = useGridCanvasNodes({
    rooms: rows,
    exits: [],
    floor: 0,
    selectedRoomId: selectedAreaId,
    onSelectRoom: onSelectArea,
    nodeType: 'room',
    buildNodeData: (area) => ({ area }),
    onPlaceRoom,
  });

  return (
    <MapCanvasShell
      testId="area-arrange-canvas"
      nodes={nodes}
      edges={edges}
      nodeTypes={nodeTypes}
      onNodesChange={onNodesChange}
      onNodeDragStop={onNodeDragStop}
      snapToGrid
      snapGrid={[CELL, CELL]}
      backgroundGap={CELL}
      minZoom={0.05}
      showMiniMap
      emptyState={
        childAreas.length === 0 ? (
          <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
            No child areas to arrange.
          </div>
        ) : undefined
      }
    />
  );
}

/**
 * AreaTreePanel — left rail of the staff world-builder canvas (#2449): a
 * minimal recursive area tree. No `ui/` Tree primitive exists yet in this
 * repo, and this is small/dig-specific enough to build inline rather than
 * invent one. Fetches roots (`has_parent=false`) up front; a node's children
 * (`parent=<id>`) are fetched lazily, only once that node is expanded.
 */
import { useState } from 'react';
import { ChevronDown, ChevronRight, Plus } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

import { useWorldBuilderAreasQuery } from '../queries';
import type { WorldBuilderArea } from '../types';

export interface AreaTreePanelProps {
  selectedAreaId: number | null;
  onSelectArea: (areaId: number) => void;
  /** `parentId` is null for a new root area. */
  onCreateArea: (parentId: number | null) => void;
}

export function AreaTreePanel({ selectedAreaId, onSelectArea, onCreateArea }: AreaTreePanelProps) {
  const { data, isLoading } = useWorldBuilderAreasQuery({ hasParent: false });
  const roots = data?.results ?? [];

  return (
    <div className="flex h-full flex-col gap-1 overflow-y-auto p-2" data-testid="area-tree-panel">
      <div className="flex items-center justify-between px-1">
        <h3 className="text-sm font-semibold">Areas</h3>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="h-6 w-6 p-0"
          onClick={() => onCreateArea(null)}
          title="New root area"
          data-testid="area-tree-new-root"
        >
          <Plus className="h-4 w-4" />
        </Button>
      </div>
      {isLoading && <p className="px-1 text-xs text-muted-foreground">Loading…</p>}
      {!isLoading && roots.length === 0 && (
        <p className="px-1 text-xs text-muted-foreground">No areas yet.</p>
      )}
      {roots.map((area) => (
        <AreaTreeNode
          key={area.id}
          area={area}
          depth={0}
          selectedAreaId={selectedAreaId}
          onSelectArea={onSelectArea}
          onCreateArea={onCreateArea}
        />
      ))}
    </div>
  );
}

interface AreaTreeNodeProps {
  area: WorldBuilderArea;
  depth: number;
  selectedAreaId: number | null;
  onSelectArea: (areaId: number) => void;
  onCreateArea: (parentId: number | null) => void;
}

function AreaTreeNode({
  area,
  depth,
  selectedAreaId,
  onSelectArea,
  onCreateArea,
}: AreaTreeNodeProps) {
  const [expanded, setExpanded] = useState(false);
  const hasChildren = area.children_count > 0;
  const { data } = useWorldBuilderAreasQuery({ parent: area.id }, expanded && hasChildren);
  const children = data?.results ?? [];

  return (
    <div>
      <div
        className={cn(
          'flex items-center gap-1 rounded px-1 py-0.5 hover:bg-accent',
          selectedAreaId === area.id && 'bg-accent'
        )}
        style={{ paddingLeft: depth * 14 }}
      >
        <button
          type="button"
          className="flex h-4 w-4 shrink-0 items-center justify-center text-muted-foreground disabled:opacity-30"
          onClick={() => setExpanded((prev) => !prev)}
          disabled={!hasChildren}
          data-testid={`area-tree-expand-${area.id}`}
          aria-label={expanded ? 'Collapse' : 'Expand'}
        >
          {hasChildren &&
            (expanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />)}
        </button>
        <button
          type="button"
          className="flex-1 truncate text-left text-sm"
          onClick={() => onSelectArea(area.id)}
          data-testid="area-tree-node"
          data-area-id={area.id}
        >
          {area.name}
          <span className="ml-1.5 text-[10px] uppercase tracking-wide text-muted-foreground">
            {area.origin}
          </span>
        </button>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="h-5 w-5 p-0"
          onClick={() => onCreateArea(area.id)}
          title={`New area under ${area.name}`}
          data-testid={`area-tree-new-child-${area.id}`}
        >
          <Plus className="h-3 w-3" />
        </Button>
      </div>
      {expanded &&
        children.map((child) => (
          <AreaTreeNode
            key={child.id}
            area={child}
            depth={depth + 1}
            selectedAreaId={selectedAreaId}
            onSelectArea={onSelectArea}
            onCreateArea={onCreateArea}
          />
        ))}
    </div>
  );
}

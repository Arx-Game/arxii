/**
 * IndexRail (#3477 Task 4) — the Atlas's persistent scoped index: a
 * lazy-expand area tree (mirrors `AreaTreePanel`'s expand-on-demand pattern —
 * roots up front, a node's children only once expanded), an "Unpublished
 * rooms" jump list, Pinned bookmarks, and Recent visits.
 *
 * The warrant scope blurb is copy-only in this task: the read API
 * (`world.areas.builder_views`) is still `IsAdminUser`-gated, so a non-staff
 * GM can't call it at all yet — actual GM-subtree read-scoping needs a
 * backend change outside this task's file list. `is_staff`/`is_gm` only pick
 * which sentence is shown here.
 *
 * "Unpublished rooms" is scoped to the CURRENTLY OPEN area's own direct rooms
 * (from the same `useAreaManagerQuery` the open `AreaPage` already fetches —
 * react-query dedups the request), not the whole warrant: `WorldBuilderArea`
 * carries no unpublished-room rollup, and computing one across an arbitrary
 * subtree would mean fetching every area's manager payload up front. A true
 * cross-area rollup needs a backend aggregate this task doesn't add.
 */
import { useState } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';

import { cn } from '@/lib/utils';
import { useAccount } from '@/store/hooks';

import { useAreaManagerQuery, useWorldBuilderAreasQuery } from '../queries';
import type { WorldBuilderArea } from '../types';
import type { AtlasHistoryEntry, AtlasView } from './useAtlasState';

/** Mirrors `world.areas.constants.AreaLevel.BUILDING` (see `types.ts`'s `AREA_LEVELS`). */
const BUILDING_LEVEL = 10;

export interface IndexRailProps {
  current: AtlasView | null;
  onSelect: (view: AtlasView, name: string) => void;
  pinned: AtlasHistoryEntry[];
  recents: AtlasHistoryEntry[];
}

export function IndexRail({ current, onSelect, pinned, recents }: IndexRailProps) {
  const account = useAccount();
  const { data: rootsPage, isLoading } = useWorldBuilderAreasQuery({ hasParent: false });
  const roots = rootsPage?.results ?? [];

  return (
    <aside
      className="flex h-full flex-col overflow-y-auto border-r bg-card"
      aria-label="Your territory"
      data-testid="index-rail"
    >
      <div className="border-b px-4 py-3">
        <h1 className="theme-heading text-base font-semibold [font-variant:small-caps]">
          The Atlas
        </h1>
        <p
          className="mt-1 font-body text-xs italic text-muted-foreground"
          data-testid="index-scope"
        >
          {account?.is_staff
            ? 'Staff warrant: every area.'
            : account?.is_gm
              ? "Your GM warrant roots at the areas you've been granted."
              : 'Read-only.'}
        </p>
      </div>

      <div className="flex-1 py-2" data-testid="index-tree">
        {isLoading && <p className="px-4 text-xs text-muted-foreground">Loading…</p>}
        {roots.map((area) => (
          <TreeNode key={area.id} area={area} depth={0} current={current} onSelect={onSelect} />
        ))}
      </div>

      <UnpublishedJump current={current} onSelect={onSelect} />
      <IndexSection
        title="Pinned"
        testId="index-pinned"
        entries={pinned}
        onSelect={onSelect}
        empty="Nothing pinned yet."
      />
      <IndexSection
        title="Recent"
        testId="index-recent"
        entries={recents}
        onSelect={onSelect}
        empty="Nothing visited yet."
      />
    </aside>
  );
}

interface TreeNodeProps {
  area: WorldBuilderArea;
  depth: number;
  current: AtlasView | null;
  onSelect: (view: AtlasView, name: string) => void;
}

function TreeNode({ area, depth, current, onSelect }: TreeNodeProps) {
  const [expanded, setExpanded] = useState(false);
  const isLeaf = area.level === BUILDING_LEVEL;
  const { data: childAreasPage } = useWorldBuilderAreasQuery(
    { parent: area.id },
    expanded && !isLeaf
  );
  const { data: manager } = useAreaManagerQuery(expanded && isLeaf ? area.id : null);
  const childAreas = childAreasPage?.results ?? [];
  const rooms = manager?.rooms ?? [];
  const isCurrent =
    current != null &&
    current.id === area.id &&
    (current.kind === 'area' || current.kind === 'roomgrid');

  return (
    <div>
      <div
        className={cn(
          'flex items-center gap-1 border-l-2 border-transparent py-1 pr-2',
          isCurrent && 'border-l-primary bg-background'
        )}
        style={{ paddingLeft: 8 + depth * 14 }}
      >
        <button
          type="button"
          onClick={() => setExpanded((prev) => !prev)}
          className="flex h-4 w-4 shrink-0 items-center justify-center text-muted-foreground"
          aria-label={expanded ? `Collapse ${area.name}` : `Expand ${area.name}`}
          data-testid={`index-expand-${area.id}`}
        >
          {expanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
        </button>
        <button
          type="button"
          className="flex-1 truncate text-left text-sm"
          onClick={() => onSelect({ kind: isLeaf ? 'roomgrid' : 'area', id: area.id }, area.name)}
          data-testid="index-area-node"
          data-area-id={area.id}
        >
          {area.name}
          <span className="ml-1.5 text-[0.6rem] uppercase tracking-wide text-muted-foreground">
            {area.level_display}
          </span>
        </button>
      </div>
      {expanded && (
        <div>
          {childAreas.map((child) => (
            <TreeNode
              key={child.id}
              area={child}
              depth={depth + 1}
              current={current}
              onSelect={onSelect}
            />
          ))}
          {rooms.map((room) => (
            <button
              key={room.id}
              type="button"
              className="flex w-full items-center gap-1.5 py-0.5 pr-2 text-left text-sm text-muted-foreground hover:text-foreground"
              style={{ paddingLeft: 8 + (depth + 1) * 14 }}
              onClick={() => onSelect({ kind: 'roomdoc', id: room.id }, room.name)}
              data-testid="index-room-node"
            >
              <span className="truncate">{room.name}</span>
              {!room.published_at && (
                <span
                  className="text-[0.6rem] uppercase tracking-wide text-muted-foreground"
                  data-testid="index-room-unpublished"
                >
                  unpublished
                </span>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

interface UnpublishedJumpProps {
  current: AtlasView | null;
  onSelect: (view: AtlasView, name: string) => void;
}

function UnpublishedJump({ current, onSelect }: UnpublishedJumpProps) {
  const areaId =
    current && (current.kind === 'area' || current.kind === 'roomgrid') ? current.id : null;
  const { data: manager } = useAreaManagerQuery(areaId);
  const unpublished = (manager?.rooms ?? []).filter((room) => !room.published_at);

  if (areaId == null || unpublished.length === 0) return null;

  return (
    <div className="border-t px-2 py-2" data-testid="index-unpublished">
      <div className="px-2 text-[0.66rem] uppercase tracking-wide text-muted-foreground">
        Unpublished rooms — {unpublished.length}
      </div>
      {unpublished.map((room) => (
        <button
          key={room.id}
          type="button"
          className="block w-full truncate px-2 py-1 text-left text-sm hover:bg-accent"
          onClick={() => onSelect({ kind: 'roomdoc', id: room.id }, room.name)}
          data-testid="index-unpublished-room"
        >
          {room.name}
        </button>
      ))}
    </div>
  );
}

interface IndexSectionProps {
  title: string;
  testId: string;
  entries: AtlasHistoryEntry[];
  onSelect: (view: AtlasView, name: string) => void;
  empty: string;
}

function IndexSection({ title, testId, entries, onSelect, empty }: IndexSectionProps) {
  return (
    <div className="border-t px-2 py-2" data-testid={testId}>
      <div className="px-2 text-[0.66rem] uppercase tracking-wide text-muted-foreground">
        {title}
      </div>
      {entries.length === 0 && (
        <p className="px-2 py-1 font-body text-xs italic text-muted-foreground">{empty}</p>
      )}
      {entries.map((entry) => (
        <button
          key={`${entry.kind}-${entry.id}`}
          type="button"
          className="block w-full truncate px-2 py-1 text-left text-sm hover:bg-accent"
          onClick={() => onSelect(entry, entry.name)}
        >
          {entry.name}
        </button>
      ))}
    </div>
  );
}

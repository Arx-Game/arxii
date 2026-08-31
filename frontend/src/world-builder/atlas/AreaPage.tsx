/**
 * AreaPage (#3477 Task 4) — one Atlas page: an area's header, its children as
 * ledger rows, and the lattice slot Task 5's `<Lattice/>` mounts into.
 *
 * "Children" branches on the area's own level (mirrors the prototype's
 * ward-vs-building split): an area above BUILDING can hold child areas
 * (fetched lazily here) *and* direct rooms of its own (open-air rooms sitting
 * right on the ward, not inside any building) — both render as ledger rows.
 * A BUILDING-level area holds only rooms, and those rooms are the lattice's
 * job to draw (Task 5), not a ledger — so a building page skips the ledger
 * entirely and goes straight to the lattice slot.
 *
 * Per-child "unpublished" counts (a BUILDING child's own room tally) cost one
 * extra `useAreaManagerQuery` per BUILDING child currently listed in this
 * ledger — bounded by this area's own direct children, not the whole tree,
 * so it stays cheap; see `ChildAreaRow`.
 */
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

import { useAreaManagerQuery, useWorldBuilderAreasQuery } from '../queries';
import type { WorldBuilderArea, WorldBuilderRoom } from '../types';
import type { AtlasView, AtlasViewKind } from './useAtlasState';

/** Mirrors `world.areas.constants.AreaLevel.BUILDING` (see `types.ts`'s `AREA_LEVELS`). */
const BUILDING_LEVEL = 10;

export interface AreaPageProps {
  areaId: number;
  onDescend: (next: AtlasView) => void;
  onOpenAreaDoc: (areaId: number) => void;
}

function childKind(area: WorldBuilderArea): AtlasViewKind {
  return area.level === BUILDING_LEVEL ? 'roomgrid' : 'area';
}

export function AreaPage({ areaId, onDescend, onOpenAreaDoc }: AreaPageProps) {
  const { data: manager, isLoading } = useAreaManagerQuery(areaId);
  const area = manager?.area;
  const isBuilding = area?.level === BUILDING_LEVEL;

  const { data: childrenPage } = useWorldBuilderAreasQuery(
    { parent: areaId },
    area != null && !isBuilding
  );
  const childAreas = childrenPage?.results ?? [];
  const rooms = manager?.rooms ?? [];

  if (isLoading || !area) {
    return (
      <div className="p-8 text-sm text-muted-foreground" data-testid="area-page-loading">
        Loading…
      </div>
    );
  }

  return (
    <section className="max-w-5xl px-8 py-6" data-testid="area-page">
      <header className="flex items-baseline gap-3">
        <h2 className="theme-heading text-2xl font-semibold [font-variant:small-caps]">
          {area.name}
        </h2>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="text-muted-foreground"
          onClick={() => onOpenAreaDoc(areaId)}
        >
          ✎ Edit
        </Button>
      </header>
      <p className="mt-1 font-body text-sm italic text-muted-foreground">
        {area.description || 'Nothing written yet.'}
      </p>

      {!isBuilding && (
        <div
          className="mt-4 divide-y border-t-2 border-t-primary"
          role="list"
          data-testid="area-ledger"
        >
          {childAreas.map((child) => (
            <ChildAreaRow key={`area-${child.id}`} area={child} onSelect={onDescend} />
          ))}
          {rooms.map((room) => (
            <LedgerRoomRow key={`room-${room.id}`} room={room} onSelect={onDescend} />
          ))}
          <button
            type="button"
            disabled
            title="Realizing a plan wires up once the lattice lands."
            className="flex w-full items-center gap-2 px-1 py-2 text-left font-body text-sm italic text-muted-foreground disabled:cursor-default disabled:opacity-70"
            data-testid="area-add-row"
          >
            ⊕ add a building, or dig an open-air room…
          </button>
        </div>
      )}

      <div data-testid="lattice-slot" className="mt-6" />
    </section>
  );
}

interface ChildAreaRowProps {
  area: WorldBuilderArea;
  onSelect: (next: AtlasView) => void;
}

function ChildAreaRow({ area, onSelect }: ChildAreaRowProps) {
  const isLeaf = area.level === BUILDING_LEVEL;
  const { data: leafManager } = useAreaManagerQuery(isLeaf ? area.id : null);
  const unpublishedCount = isLeaf
    ? (leafManager?.rooms ?? []).filter((room) => !room.published_at).length
    : null;

  return (
    <button
      type="button"
      className="grid w-full grid-cols-[1fr_auto_auto] items-baseline gap-4 px-1 py-2 text-left hover:bg-accent"
      onClick={() => onSelect({ kind: childKind(area), id: area.id })}
      data-testid="ledger-area-row"
    >
      <span className="theme-heading text-base [font-variant:small-caps]">{area.name}</span>
      <span className="text-[0.65rem] uppercase tracking-wide text-muted-foreground">
        {area.level_display}
        {area.children_count > 0 ? ` · ${area.children_count} areas` : ''}
      </span>
      <span className="font-body text-xs italic text-muted-foreground">
        {unpublishedCount == null
          ? ''
          : unpublishedCount > 0
            ? `${unpublishedCount} unpublished`
            : 'published'}
      </span>
    </button>
  );
}

interface LedgerRoomRowProps {
  room: WorldBuilderRoom;
  onSelect: (next: AtlasView) => void;
}

function LedgerRoomRow({ room, onSelect }: LedgerRoomRowProps) {
  const unpublished = !room.published_at;
  return (
    <button
      type="button"
      className={cn(
        'grid w-full grid-cols-[1fr_auto_auto] items-baseline gap-4 px-1 py-2 text-left hover:bg-accent',
        unpublished && 'text-muted-foreground'
      )}
      onClick={() => onSelect({ kind: 'roomdoc', id: room.id })}
      data-testid="ledger-room-row"
    >
      <span className="theme-heading text-base [font-variant:small-caps]">{room.name}</span>
      <span className="text-[0.65rem] uppercase tracking-wide text-muted-foreground">
        open-air room
      </span>
      <span className="font-body text-xs italic text-muted-foreground">
        {unpublished ? 'unpublished' : 'published'}
      </span>
    </button>
  );
}

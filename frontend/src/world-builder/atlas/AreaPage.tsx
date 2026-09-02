/**
 * AreaPage (#3477 Task 4/5) — one Atlas page: an area's header, its children
 * as ledger rows, and the Lattice (Task 5) beneath them.
 *
 * "Children" branches on the area's own level (mirrors the prototype's
 * ward-vs-building split): an area above BUILDING can hold child areas
 * (fetched lazily here) *and* direct rooms of its own (open-air rooms sitting
 * right on the ward, not inside any building) — both render as ledger rows
 * *and* as Lattice tiles (`'areas'` mode). A BUILDING-level area holds only
 * rooms — no ledger, straight to the Lattice (`'rooms'` mode).
 *
 * The old disabled "⊕ add a building…" ledger row (Task 4 placeholder) is
 * gone — the Lattice's own empty-cell click is that affordance now, for real.
 *
 * Per-child "unpublished"/room-total counts (a BUILDING child's own room
 * tally) cost one extra `useAreaManagerQuery` per BUILDING child currently
 * listed in this ledger — bounded by this area's own direct children, not
 * the whole tree, so it stays cheap; see `ChildAreaRow`.
 */
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Plate, PlateHead } from '@/components/folio';
import { cn } from '@/lib/utils';

import { useAreaManagerQuery, useWorldBuilderAction, useWorldBuilderAreasQuery } from '../queries';
import type { WorldBuilderActionKey, WorldBuilderArea, WorldBuilderRoom } from '../types';
import { useWorldBuilderActor } from '../useWorldBuilderActor';
import { areaViewKind, BUILDING_LEVEL, childLevelOf } from './constants';
import { Lattice, type LatticeTile } from './Lattice';
import type { AtlasView } from './useAtlasState';

export interface AreaPageProps {
  areaId: number;
  onDescend: (next: AtlasView) => void;
  onOpenAreaDoc: (areaId: number) => void;
  /** A search hit landing here (#3477 Task 6) — passed straight through to the Lattice. */
  highlightRoomId?: number | null;
}

function areaToTile(area: WorldBuilderArea): LatticeTile {
  return {
    id: area.id,
    kind: 'area',
    name: area.name,
    kindLabel: area.level_display,
    unpublished: false,
    gridX: area.grid_x,
    gridY: area.grid_y,
    floor: 0,
    level: area.level,
  };
}

function roomToTile(room: WorldBuilderRoom, kindLabel: string): LatticeTile {
  return {
    id: room.id,
    kind: 'room',
    name: room.name,
    kindLabel,
    unpublished: !room.published_at,
    gridX: room.grid_x,
    gridY: room.grid_y,
    floor: room.floor,
  };
}

export function AreaPage({
  areaId,
  onDescend,
  onOpenAreaDoc,
  highlightRoomId = null,
}: AreaPageProps) {
  const { data: manager, isLoading } = useAreaManagerQuery(areaId);
  const area = manager?.area;
  const isBuilding = area?.level === BUILDING_LEVEL;

  const { data: childrenPage } = useWorldBuilderAreasQuery(
    { parent: areaId },
    area != null && !isBuilding
  );
  const childAreas = childrenPage?.results ?? [];
  const rooms = manager?.rooms ?? [];

  const characterId = useWorldBuilderActor();
  const { mutate: runMutation } = useWorldBuilderAction(characterId ?? 0, areaId);
  const runAction = (key: string, kwargs: Record<string, unknown>) => {
    if (characterId == null) {
      toast.error(
        'Select a character to build as; builder actions dispatch through your played character.'
      );
      return;
    }
    runMutation({ key: key as WorldBuilderActionKey, kwargs });
  };

  if (isLoading || !area) {
    return (
      <div className="p-8 text-sm text-muted-foreground" data-testid="area-page-loading">
        Loading…
      </div>
    );
  }

  const tiles: LatticeTile[] = isBuilding
    ? rooms.map((room) => roomToTile(room, 'room'))
    : [...childAreas.map(areaToTile), ...rooms.map((room) => roomToTile(room, 'open-air room'))];

  const handleLatticeOpen = (tile: LatticeTile) => {
    if (tile.kind === 'area') {
      onDescend({ kind: areaViewKind(tile.level ?? BUILDING_LEVEL), id: tile.id });
    } else {
      onDescend({ kind: 'roomdoc', id: tile.id });
    }
  };

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
        <Plate className="mt-4 divide-y p-0" role="list" data-testid="area-ledger">
          {childAreas.map((child) => (
            <ChildAreaRow key={`area-${child.id}`} area={child} onSelect={onDescend} />
          ))}
          {rooms.map((room) => (
            <LedgerRoomRow key={`room-${room.id}`} room={room} onSelect={onDescend} />
          ))}
        </Plate>
      )}

      <div className="mt-6" data-testid="lattice-slot">
        <Lattice
          mode={isBuilding ? 'rooms' : 'areas'}
          nodeId={areaId}
          tiles={tiles}
          onOpen={handleLatticeOpen}
          runAction={runAction}
          childAreaLevel={isBuilding ? undefined : childLevelOf(area.level)}
          highlightTileId={highlightRoomId}
        />
      </div>
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
  const leafRooms = leafManager?.rooms ?? [];
  const unpublishedCount = isLeaf ? leafRooms.filter((room) => !room.published_at).length : null;

  const kindMeta = isLeaf
    ? leafManager
      ? `${area.level_display} · ${leafRooms.length} room${leafRooms.length === 1 ? '' : 's'}`
      : area.level_display
    : `${area.level_display}${area.children_count > 0 ? ` · ${area.children_count} areas` : ''}`;

  const renderUnpublishedCount = () => {
    if (unpublishedCount == null) {
      return '';
    }
    if (unpublishedCount > 0) {
      return `${unpublishedCount} unpublished`;
    }
    return 'published';
  };

  return (
    <button
      type="button"
      className="grid w-full grid-cols-[1fr_auto_auto] items-baseline gap-4 px-3 py-2 text-left hover:bg-accent"
      onClick={() => onSelect({ kind: areaViewKind(area.level), id: area.id })}
      data-testid="ledger-area-row"
    >
      <span className="theme-heading text-base [font-variant:small-caps]">{area.name}</span>
      <PlateHead as="span" className="text-[0.65rem] tracking-wide" data-testid="ledger-area-kind">
        {kindMeta}
      </PlateHead>
      <span className="font-body text-xs italic text-muted-foreground">
        {renderUnpublishedCount()}
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
        'grid w-full grid-cols-[1fr_auto_auto] items-baseline gap-4 px-3 py-2 text-left hover:bg-accent',
        unpublished && 'text-muted-foreground'
      )}
      onClick={() => onSelect({ kind: 'roomdoc', id: room.id })}
      data-testid="ledger-room-row"
    >
      <span className="theme-heading text-base [font-variant:small-caps]">{room.name}</span>
      <PlateHead as="span" className="text-[0.65rem] tracking-wide">
        open-air room
      </PlateHead>
      <span className="font-body text-xs italic text-muted-foreground">
        {unpublished ? 'unpublished' : 'published'}
      </span>
    </button>
  );
}

/**
 * AtlasPage (#3477 Task 4) — the Commonplace Atlas shell: `/staff/world-builder`'s
 * new home, replacing the old three-panel `WorldBuilderPage` (retired in Task 8
 * once every view it covers has a new-shell equivalent).
 *
 * Owns navigation state (`useAtlasState`) and routes the current view to its
 * body: an area (ward-or-building alike — `AreaPage` branches on level), a
 * room's manuscript ('roomdoc', Task 6's `RoomDocument`), or an area's
 * document ('areadoc', Task 7's `AreaDocument`).
 *
 * `lens` is the read-only visitor seam from the spec (§1): a typed prop union
 * with exactly one implemented member. Every render below assumes the
 * warrant lens (staff/GM, read-write); a future 'visitor' lens would need its
 * own read-only bodies, not built here.
 *
 * Search-hit navigation (spec §1, upgraded Task 6): a hit lands on its
 * PARENT grid with the room highlighted, not straight into the room
 * document — the T4 interim behavior (open the manuscript directly) was a
 * placeholder wired against `roomdoc-placeholder`, since there was nothing
 * else to land on yet. `highlightRoomId` is plain local state (not part of
 * `useAtlasState`'s persisted trail — a highlight is a one-shot visual cue,
 * never something worth remembering across a reload) that self-clears after
 * a few seconds.
 *
 * Growing the ladder from the crumb (2026-09-09): a ⊕ between two crumb
 * entries opens `InsertLevelDialog`; confirming dispatches `create_area`
 * under the upper entry at the lower entry's spot on that map, then moves the
 * lower entry inside (`staff_move_room` + `staff_place_room` at the origin
 * for a room, `edit_area` with the new parent for an area). Each step's
 * result gates the next, so a refused create leaves nothing half-moved.
 */
import { useEffect, useState } from 'react';
import { toast } from 'sonner';

import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';

import { AreaDocument } from '../document/AreaDocument';
import { RoomDocument } from '../document/RoomDocument';
import {
  useAreaManagerQuery,
  useMyGrantsQuery,
  useRoomDetailQuery,
  useRoomSearchQuery,
  useWorldBuilderAction,
  useWorldBuilderAreasQuery,
} from '../queries';
import type { WorldBuilderActionKey } from '../types';
import { useWorldBuilderActor } from '../useWorldBuilderActor';
import { AreaPage } from './AreaPage';
import { areaViewKind } from './constants';
import { FolioCrumb, type FolioCrumbEntry } from './FolioCrumb';
import { IndexRail } from './IndexRail';
import { InsertLevelDialog } from './InsertLevelDialog';
import { useAtlasState, type AtlasView } from './useAtlasState';

/** A crumb entry plus where it sits on its parent's map, for the insert chain. */
interface PlacedCrumbEntry extends FolioCrumbEntry {
  grid_x: number | null;
  grid_y: number | null;
  floor?: number;
}

function slugify(value: string): string {
  const slug = value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-/, '')
    .replace(/-$/, '');
  return slug || 'area';
}

/** How long a search-hit highlight ring stays lit before fading on its own. */
const HIGHLIGHT_DURATION_MS = 2500;

export interface AtlasPageProps {
  /** The read-only visitor lens (spec §1) — typed now, NOT implemented. */
  lens?: 'warrant';
}

export function AtlasPage({ lens = 'warrant' }: AtlasPageProps) {
  void lens; // seam only — every body below assumes the warrant lens

  const { view, setView, pinned, isPinned, togglePinned, recents } = useAtlasState();
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const [highlightRoomId, setHighlightRoomId] = useState<number | null>(null);

  useEffect(() => {
    if (highlightRoomId == null) return;
    const timer = window.setTimeout(() => setHighlightRoomId(null), HIGHLIGHT_DURATION_MS);
    return () => window.clearTimeout(timer);
  }, [highlightRoomId]);

  const { data: rootsPage } = useWorldBuilderAreasQuery({ hasParent: false });
  const { data: myGrants } = useMyGrantsQuery();
  useEffect(() => {
    if (view != null) return;
    // Warrant rooting (#3534, spec §1): a granted GM's atlas opens at the top
    // of their warrant, not the world — for them the roots query is empty
    // anyway (their subtree's root has a parent, and reads are scoped).
    const grant = myGrants != null && !myGrants.is_staff ? myGrants.grants[0] : undefined;
    if (grant) {
      setView({ kind: areaViewKind(grant.area_level), id: grant.area_id }, grant.area_name);
      return;
    }
    const firstRoot = rootsPage?.results?.[0];
    if (firstRoot) {
      setView({ kind: areaViewKind(firstRoot.level), id: firstRoot.id }, firstRoot.name);
    }
  }, [view, rootsPage, myGrants, setView]);

  const isRoomDoc = view?.kind === 'roomdoc';
  // 'areadoc' included: the area document is the area, so the manager query
  // feeds its crumb and pin name the same way the grid views' do.
  const areaId =
    view && (view.kind === 'area' || view.kind === 'roomgrid' || view.kind === 'areadoc')
      ? view.id
      : null;
  const { data: manager } = useAreaManagerQuery(areaId);
  const { data: roomDetail } = useRoomDetailQuery(isRoomDoc ? view.id : null);
  const { data: searchResults } = useRoomSearchQuery(searchTerm);

  const crumbEntries: PlacedCrumbEntry[] =
    isRoomDoc && roomDetail
      ? [
          ...roomDetail.breadcrumb,
          {
            id: roomDetail.room.id,
            name: roomDetail.room.name,
            kind: 'room' as const,
            grid_x: roomDetail.room.grid_x,
            grid_y: roomDetail.room.grid_y,
            floor: roomDetail.room.floor,
          },
        ]
      : (manager?.breadcrumb ?? []);

  const characterId = useWorldBuilderActor();
  const { mutateAsync: runMutation } = useWorldBuilderAction(characterId ?? 0, areaId);
  const [insertBetween, setInsertBetween] = useState<{
    upper: PlacedCrumbEntry;
    lower: PlacedCrumbEntry;
  } | null>(null);

  const insertLevel = async (name: string, level: number) => {
    if (!insertBetween) return;
    const { upper, lower } = insertBetween;
    if (characterId == null) {
      toast.error(
        'Select a character to build as; builder actions dispatch through your played character.'
      );
      return;
    }
    const run = async (key: WorldBuilderActionKey, kwargs: Record<string, unknown>) => {
      try {
        return await runMutation({ key, kwargs });
      } catch {
        return undefined;
      }
    };
    const created = await run('create_area', {
      name,
      slug: slugify(name),
      level,
      parent_id: upper.id,
      grid_x: lower.grid_x,
      grid_y: lower.grid_y,
    });
    const newAreaId = created?.data?.area_id;
    if (typeof newAreaId !== 'number') return;
    if (lower.kind === 'room') {
      const moved = await run('staff_move_room', { room_id: lower.id, area_id: newAreaId });
      if (moved?.success === false) return;
      await run('staff_place_room', {
        room_id: lower.id,
        grid_x: 0,
        grid_y: 0,
        floor: lower.floor ?? 0,
      });
    } else {
      await run('edit_area', { area_id: lower.id, parent_id: newAreaId, grid_x: 0, grid_y: 0 });
    }
  };

  const handleSelect = (next: AtlasView, name?: string) => setView(next, name ?? `#${next.id}`);
  /** "Next unpublished"/Compass-neighbor navigation (#3477 Task 6) — a plain
   * view swap, deliberately NOT recorded into Recent (no `name` passed). */
  const handleNavigateRoom = (roomId: number) => handleSelect({ kind: 'roomdoc', id: roomId });

  const renderView = () => {
    if (view?.kind === 'area' || view?.kind === 'roomgrid') {
      return (
        <AreaPage
          areaId={view.id}
          onDescend={handleSelect}
          onOpenAreaDoc={(id) => handleSelect({ kind: 'areadoc', id })}
          highlightRoomId={highlightRoomId}
        />
      );
    }
    if (view?.kind === 'roomdoc') {
      return (
        <RoomDocument
          roomId={view.id}
          onNavigateRoom={handleNavigateRoom}
          onDeleted={(deletedAreaId) => handleSelect({ kind: 'roomgrid', id: deletedAreaId })}
        />
      );
    }
    if (view?.kind === 'areadoc') {
      return (
        <AreaDocument
          areaId={view.id}
          onDeleted={(parentAreaId) => {
            // Land on the parent's grid; a deleted root falls back to the
            // first root (the same default the view==null effect uses).
            if (parentAreaId != null) {
              handleSelect({ kind: 'area', id: parentAreaId });
            } else {
              const firstRoot = rootsPage?.results?.[0];
              if (firstRoot) {
                handleSelect({ kind: areaViewKind(firstRoot.level), id: firstRoot.id });
              }
            }
          }}
        />
      );
    }
    return (
      <div className="p-8 text-sm text-muted-foreground" data-testid="atlas-loading">
        Loading the atlas…
      </div>
    );
  };

  return (
    <div className="grid h-screen grid-cols-[270px_1fr]" data-testid="atlas-page">
      <IndexRail
        current={view}
        onSelect={handleSelect}
        pinned={pinned}
        recents={recents}
        grants={myGrants != null && !myGrants.is_staff ? myGrants.grants : []}
      />

      <main className="overflow-y-auto">
        <FolioCrumb
          entries={crumbEntries}
          onSelect={(id) => handleSelect({ kind: 'area', id })}
          onInsertBetween={(upper, lower) =>
            setInsertBetween({ upper: upper as PlacedCrumbEntry, lower: lower as PlacedCrumbEntry })
          }
        >
          {view && (
            <button
              type="button"
              className="text-muted-foreground hover:text-primary"
              onClick={() =>
                togglePinned({
                  ...view,
                  name: isRoomDoc
                    ? (roomDetail?.room.name ?? `#${view.id}`)
                    : (manager?.area.name ?? `#${view.id}`),
                  visitedAt: new Date().toISOString(),
                })
              }
              data-testid="pin-toggle"
            >
              {isPinned(view) ? '★ pinned' : '☆ pin'}
            </button>
          )}
          <button
            type="button"
            className="text-muted-foreground hover:text-primary"
            onClick={() => setSearchOpen(true)}
            data-testid="open-room-search"
          >
            ⌕ find a room
          </button>
        </FolioCrumb>

        {renderView()}
      </main>

      <InsertLevelDialog
        between={insertBetween}
        onClose={() => setInsertBetween(null)}
        onConfirm={({ name, level }) => void insertLevel(name, level)}
      />

      <Dialog open={searchOpen} onOpenChange={setSearchOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Find a room</DialogTitle>
          </DialogHeader>
          <Input
            autoFocus
            placeholder="start typing — kitchen, portico, stair…"
            value={searchTerm}
            onChange={(event) => setSearchTerm(event.target.value)}
            data-testid="room-search-input"
          />
          <div className="grid min-h-[4rem] gap-1" aria-live="polite">
            {searchTerm.trim().length < 2 && (
              <p className="font-body text-xs italic text-muted-foreground">
                Type at least 2 characters…
              </p>
            )}
            {(searchResults ?? []).map((hit) => (
              <button
                key={hit.id}
                type="button"
                className="px-2 py-1 text-left text-sm hover:bg-accent"
                onClick={() => {
                  // Land on the room's parent grid, highlighted — not
                  // straight into its manuscript (spec §1). A room with no
                  // area at all (shouldn't normally happen) falls back to
                  // opening its document directly, since there's no grid
                  // to land on.
                  if (hit.area_id != null) {
                    handleSelect({ kind: 'roomgrid', id: hit.area_id });
                    setHighlightRoomId(hit.id);
                  } else {
                    handleSelect({ kind: 'roomdoc', id: hit.id }, hit.name);
                  }
                  setSearchOpen(false);
                }}
                data-testid="room-search-hit"
              >
                {hit.name}
                {hit.area_name && (
                  <span className="ml-2 text-xs text-muted-foreground">{hit.area_name}</span>
                )}
              </button>
            ))}
          </div>
          <p className="text-right font-body text-xs italic text-muted-foreground">
            searches every room inside your warrant
          </p>
        </DialogContent>
      </Dialog>
    </div>
  );
}

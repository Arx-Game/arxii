/**
 * AtlasPage (#3477 Task 4) — the Commonplace Atlas shell: `/staff/world-builder`'s
 * new home, replacing the old three-panel `WorldBuilderPage` (retired in Task 8
 * once every view it covers has a new-shell equivalent).
 *
 * Owns navigation state (`useAtlasState`) and routes the current view to its
 * body: an area (ward-or-building alike — `AreaPage` branches on level), a
 * room's manuscript ('roomdoc', Task 6's `RoomDocument`), or an area's
 * document ('areadoc', mounted by Task 7's `AreaDocument` — still a
 * placeholder here until that task lands).
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
 */
import { useEffect, useState } from 'react';

import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';

import { RoomDocument } from '../document/RoomDocument';
import {
  useAreaManagerQuery,
  useRoomDetailQuery,
  useRoomSearchQuery,
  useWorldBuilderAreasQuery,
} from '../queries';
import { AreaPage } from './AreaPage';
import { areaViewKind } from './constants';
import { FolioCrumb, type FolioCrumbEntry } from './FolioCrumb';
import { IndexRail } from './IndexRail';
import { useAtlasState, type AtlasView } from './useAtlasState';

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
  useEffect(() => {
    if (view != null) return;
    const firstRoot = rootsPage?.results?.[0];
    if (firstRoot) {
      setView({ kind: areaViewKind(firstRoot.level), id: firstRoot.id }, firstRoot.name);
    }
  }, [view, rootsPage, setView]);

  const isRoomDoc = view?.kind === 'roomdoc';
  const areaId = view && (view.kind === 'area' || view.kind === 'roomgrid') ? view.id : null;
  const { data: manager } = useAreaManagerQuery(areaId);
  const { data: roomDetail } = useRoomDetailQuery(isRoomDoc ? view.id : null);
  const { data: searchResults } = useRoomSearchQuery(searchTerm);

  const crumbEntries: FolioCrumbEntry[] =
    isRoomDoc && roomDetail
      ? [...roomDetail.breadcrumb, { id: roomDetail.room.id, name: roomDetail.room.name }]
      : (manager?.breadcrumb ?? []);

  const handleSelect = (next: AtlasView, name?: string) => setView(next, name ?? `#${next.id}`);
  /** "Next unpublished"/Compass-neighbor navigation (#3477 Task 6) — a plain
   * view swap, deliberately NOT recorded into Recent (no `name` passed). */
  const handleNavigateRoom = (roomId: number) => handleSelect({ kind: 'roomdoc', id: roomId });

  return (
    <div className="grid h-screen grid-cols-[270px_1fr]" data-testid="atlas-page">
      <IndexRail current={view} onSelect={handleSelect} pinned={pinned} recents={recents} />

      <main className="overflow-y-auto">
        <FolioCrumb entries={crumbEntries} onSelect={(id) => handleSelect({ kind: 'area', id })}>
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

        {view?.kind === 'area' || view?.kind === 'roomgrid' ? (
          <AreaPage
            areaId={view.id}
            onDescend={handleSelect}
            onOpenAreaDoc={(id) => handleSelect({ kind: 'areadoc', id })}
            highlightRoomId={highlightRoomId}
          />
        ) : view?.kind === 'roomdoc' ? (
          <RoomDocument
            roomId={view.id}
            onNavigateRoom={handleNavigateRoom}
            onDeleted={(deletedAreaId) => handleSelect({ kind: 'roomgrid', id: deletedAreaId })}
          />
        ) : view?.kind === 'areadoc' ? (
          <div className="p-8 text-sm text-muted-foreground" data-testid="areadoc-placeholder">
            The area document mounts here.
          </div>
        ) : (
          <div className="p-8 text-sm text-muted-foreground" data-testid="atlas-loading">
            Loading the atlas…
          </div>
        )}
      </main>

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

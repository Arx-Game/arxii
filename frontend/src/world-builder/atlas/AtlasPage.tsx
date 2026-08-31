/**
 * AtlasPage (#3477 Task 4) — the Commonplace Atlas shell: `/staff/world-builder`'s
 * new home, replacing the old three-panel `WorldBuilderPage` (retired in Task 8
 * once every view it covers has a new-shell equivalent).
 *
 * Owns navigation state (`useAtlasState`) and routes the current view to its
 * body: an area (ward-or-building alike — `AreaPage` branches on level), a
 * room's manuscript ('roomdoc', mounted by Task 6's `RoomDocument`), or an
 * area's document ('areadoc', mounted by Task 7's `AreaDocument`) — both
 * placeholders here until those tasks land.
 *
 * `lens` is the read-only visitor seam from the spec (§1): a typed prop union
 * with exactly one implemented member. Every render below assumes the
 * warrant lens (staff/GM, read-write); a future 'visitor' lens would need its
 * own read-only bodies, not built here.
 */
import { useEffect, useState } from 'react';

import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';

import { useAreaManagerQuery, useRoomSearchQuery, useWorldBuilderAreasQuery } from '../queries';
import { AreaPage } from './AreaPage';
import { areaViewKind } from './constants';
import { FolioCrumb, type FolioCrumbEntry } from './FolioCrumb';
import { IndexRail } from './IndexRail';
import { useAtlasState, type AtlasView } from './useAtlasState';

export interface AtlasPageProps {
  /** The read-only visitor lens (spec §1) — typed now, NOT implemented. */
  lens?: 'warrant';
}

export function AtlasPage({ lens = 'warrant' }: AtlasPageProps) {
  void lens; // seam only — every body below assumes the warrant lens

  const { view, setView, pinned, isPinned, togglePinned, recents } = useAtlasState();
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');

  const { data: rootsPage } = useWorldBuilderAreasQuery({ hasParent: false });
  useEffect(() => {
    if (view != null) return;
    const firstRoot = rootsPage?.results?.[0];
    if (firstRoot) {
      setView({ kind: areaViewKind(firstRoot.level), id: firstRoot.id }, firstRoot.name);
    }
  }, [view, rootsPage, setView]);

  const areaId = view && (view.kind === 'area' || view.kind === 'roomgrid') ? view.id : null;
  const { data: manager } = useAreaManagerQuery(areaId);
  const { data: searchResults } = useRoomSearchQuery(searchTerm);

  const crumbEntries: FolioCrumbEntry[] = manager?.breadcrumb ?? [];

  const handleSelect = (next: AtlasView, name?: string) => setView(next, name ?? `#${next.id}`);

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
                  name: manager?.area.name ?? `#${view.id}`,
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
          />
        ) : view?.kind === 'roomdoc' ? (
          <div className="p-8 text-sm text-muted-foreground" data-testid="roomdoc-placeholder">
            The room document mounts here.
          </div>
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
                  handleSelect({ kind: 'roomdoc', id: hit.id }, hit.name);
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

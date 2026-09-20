/**
 * The Reading Room — `/journals` (#3941).
 *
 * One route, four screens, no rail: a centred stream of writing, newest first.
 * `?writer=<sheetId>` is one writer's journal, `?mine=1` is your own, and
 * everything else is the stream. Search drops down beside Write with the index
 * under it; closing it always returns you to the stream, because Search is a
 * panel and never a mode.
 *
 * The visit mark is stamped exactly once per visit: the stream asks
 * `useJournalEntries` for it, and the hook puts it on its first fetch and on no
 * later one, so "since your last visit" keeps meaning the last visit rather than
 * the last thing the reader clicked.
 *
 * Interface copy here is plain and short by ruling: no help text, no
 * explanation of what a white or a black journal is. The page is furniture;
 * the writing is the point.
 */
import { useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';

import { useBrowsingIdentity } from '@/roster/useBrowsingIdentity';
import { useAppSelector } from '@/store/hooks';

import type { JournalEntryListFilters, JournalEntrySummary } from '../api';
import { QUIET_BUTTON_CLASS, PRIMARY_BUTTON_CLASS } from '../fieldClasses';
import { useJournalEntries, useMyJournalEntries } from '../queries';
import { subjectsOf, type AboutSubject } from '../rows';
import { JournalDesk } from '../components/JournalDesk';
import { JournalRow, type RowViewer } from '../components/JournalRow';
import { SearchPanel } from '../components/SearchPanel';
import { WriterPlate, type WriterFilter } from '../components/WriterPlate';
import { YourJournalHeader } from '../components/YourJournalHeader';
import '../journals.css';

interface StreamProps {
  rows: JournalEntrySummary[];
  viewer: RowViewer;
  openId: number | null;
  onToggleRow: (id: number) => void;
  isLoading: boolean;
}

/** The stream itself: the rows, and what to say when there are none. */
function Stream({ rows, viewer, openId, onToggleRow, isLoading }: StreamProps) {
  if (isLoading) {
    return <p className="jr-sans text-[.875rem] text-muted-foreground">Loading…</p>;
  }
  if (rows.length === 0) {
    return <p className="jr-sans text-[.875rem] text-muted-foreground">Nothing here yet.</p>;
  }
  return (
    <div>
      {rows.map((row) => (
        <JournalRow
          key={row.id}
          entry={row}
          open={openId === row.id}
          onToggle={() => onToggleRow(row.id)}
          viewer={viewer}
        />
      ))}
    </div>
  );
}

function Pages({
  page,
  hasPrevious,
  hasNext,
  onPage,
}: {
  page: number;
  hasPrevious: boolean;
  hasNext: boolean;
  onPage: (page: number) => void;
}) {
  if (!hasPrevious && !hasNext) return null;
  return (
    <div className="jr-sans flex items-center gap-3 border-t pt-4 text-[.8125rem]">
      <button
        type="button"
        className={QUIET_BUTTON_CLASS}
        disabled={!hasPrevious}
        onClick={() => onPage(page - 1)}
      >
        Newer entries
      </button>
      <span className="text-muted-foreground">Page {page}</span>
      <button
        type="button"
        className={QUIET_BUTTON_CLASS}
        disabled={!hasNext}
        onClick={() => onPage(page + 1)}
      >
        Older entries
      </button>
    </div>
  );
}

function scrollEntryIntoView(id: number) {
  const element = document.querySelector(`[data-entry-id="${id}"]`);
  element?.scrollIntoView?.({ block: 'start', behavior: 'smooth' });
}

interface BodyProps {
  viewer: RowViewer;
  openId: number | null;
  onOpenRow: (id: number | null) => void;
}

/** Screen 1 — everything the reader may see, newest first, with Search over it. */
function StreamBody({
  viewer,
  openId,
  onOpenRow,
  searchOpen,
  onCloseSearch,
}: BodyProps & { searchOpen: boolean; onCloseSearch: () => void }) {
  const [filters, setFilters] = useState<JournalEntryListFilters>({});
  const [page, setPage] = useState(1);
  // `mark_visit` stays out of these filters, and so out of the query key: the hook
  // stamps the mark on its first fetch and never again.
  const query = useJournalEntries({ ...filters, page }, true);

  const rows = query.data?.results ?? [];

  return (
    <>
      <SearchPanel
        open={searchOpen}
        filters={filters}
        onFiltersChange={(next) => {
          setFilters(next);
          setPage(1);
        }}
        rows={rows}
        onOpenEntry={(id) => {
          onCloseSearch();
          onOpenRow(id);
          scrollEntryIntoView(id);
        }}
        isStaff={viewer.isStaff}
        sinceVisitCount={query.data?.since_visit_count ?? 0}
        totalCount={query.data?.count}
      />
      <Stream
        rows={rows}
        viewer={viewer}
        openId={openId}
        onToggleRow={(id) => onOpenRow(openId === id ? null : id)}
        isLoading={query.isLoading}
      />
      <Pages
        page={page}
        hasPrevious={!!query.data?.previous}
        hasNext={!!query.data?.next}
        onPage={setPage}
      />
    </>
  );
}

/**
 * Which `about` the writer's three pills ask for: the subject itself while
 * reading what they wrote about someone, the writer while reading what was
 * written about them, and nothing at all for their whole journal.
 */
function aboutFilter(filter: WriterFilter, writerId: number): number | undefined {
  if (filter.kind === 'about') return filter.aboutId;
  if (filter.kind === 'reverse') return writerId;
  return undefined;
}

/** Screen 2 — one writer, under their plate, cut three ways. */
function WriterBody({ writerId, viewer, openId, onOpenRow }: BodyProps & { writerId: number }) {
  const [filter, setFilter] = useState<WriterFilter>({ kind: 'all' });
  const [page, setPage] = useState(1);
  const [subjects, setSubjects] = useState<AboutSubject[]>([]);

  const reverse = filter.kind === 'reverse';
  const query = useJournalEntries({
    author: reverse ? undefined : writerId,
    about: aboutFilter(filter, writerId),
    page,
  });

  const rows = useMemo(() => query.data?.results ?? [], [query.data]);
  const fresh = useMemo(() => subjectsOf(rows), [rows]);

  // The About pills describe the writer, not the cut currently being read, so
  // they are remembered from the unfiltered view rather than recomputed from a
  // page that has already been narrowed to one subject.
  useEffect(() => {
    if (filter.kind === 'all' && fresh.length > 0) setSubjects(fresh);
  }, [filter.kind, fresh]);

  const name =
    rows.find((row) => row.author === writerId)?.author_name ??
    rows.find((row) => row.about === writerId)?.about_name ??
    null;

  return (
    <>
      <WriterPlate
        writerId={writerId}
        name={name}
        counts={{
          entries: query.data?.count ?? 0,
          black: rows.filter((row) => !row.is_public && !row.revealed_at).length,
        }}
        subjects={subjects}
        filter={filter}
        onFilter={(next) => {
          setFilter(next);
          setPage(1);
        }}
      />
      <Stream
        rows={rows}
        viewer={viewer}
        openId={openId}
        onToggleRow={(id) => onOpenRow(openId === id ? null : id)}
        isLoading={query.isLoading}
      />
      <Pages
        page={page}
        hasPrevious={!!query.data?.previous}
        hasNext={!!query.data?.next}
        onPage={setPage}
      />
    </>
  );
}

/** Screen 4 — your own, white and black together. */
function MineBody({ viewer, openId, onOpenRow }: BodyProps) {
  const [page, setPage] = useState(1);
  const query = useMyJournalEntries(page);
  const rows = query.data?.results ?? [];

  return (
    <>
      <Stream
        rows={rows}
        viewer={viewer}
        openId={openId}
        onToggleRow={(id) => onOpenRow(openId === id ? null : id)}
        isLoading={query.isLoading}
      />
      <Pages
        page={page}
        hasPrevious={!!query.data?.previous}
        hasNext={!!query.data?.next}
        onPage={setPage}
      />
    </>
  );
}

export function JournalsPage() {
  const [searchParams] = useSearchParams();
  const identity = useBrowsingIdentity();
  const isStaff = useAppSelector((state) => state.auth.account?.is_staff) ?? false;
  const [searchOpen, setSearchOpen] = useState(false);
  const [deskOpen, setDeskOpen] = useState(false);
  const [openId, setOpenId] = useState<number | null>(null);

  const mine = searchParams.get('mine') === '1';
  const writerParam = searchParams.get('writer');
  const writerId = writerParam ? Number(writerParam) : null;
  const docked = identity.entry !== null;

  const viewer: RowViewer = useMemo(
    () => ({
      sheetId: identity.entry?.character_id ?? null,
      // The face the player is wearing (#981), never the PRIMARY persona directly.
      personaId: identity.entry?.active_persona_id ?? identity.entry?.primary_persona_id ?? null,
      isStaff,
    }),
    [identity.entry, isStaff]
  );

  const body = () => {
    if (mine) {
      return <MineBody viewer={viewer} openId={openId} onOpenRow={setOpenId} />;
    }
    if (writerId !== null && !Number.isNaN(writerId)) {
      return (
        <WriterBody writerId={writerId} viewer={viewer} openId={openId} onOpenRow={setOpenId} />
      );
    }
    return (
      <StreamBody
        viewer={viewer}
        openId={openId}
        onOpenRow={setOpenId}
        searchOpen={searchOpen}
        onCloseSearch={() => setSearchOpen(false)}
      />
    );
  };

  const onStream = !mine && (writerId === null || Number.isNaN(writerId));

  return (
    <div className="journals min-h-screen px-4 py-8">
      <div className="mx-auto max-w-[54rem]">
        <header className="mb-4 flex flex-wrap items-baseline justify-between gap-4">
          {mine ? (
            <YourJournalHeader name={identity.name ?? ''} />
          ) : (
            <h1 className="m-0 font-display text-[1.6rem] font-semibold tracking-[.04em]">
              Journals
            </h1>
          )}
          <div className="flex flex-wrap items-center gap-2">
            {onStream ? (
              <button
                type="button"
                className={QUIET_BUTTON_CLASS}
                aria-expanded={searchOpen}
                aria-controls="journal-search"
                onClick={() => setSearchOpen((previous) => !previous)}
              >
                Search
              </button>
            ) : null}
            {docked ? (
              <button
                type="button"
                className={PRIMARY_BUTTON_CLASS}
                onClick={() => setDeskOpen((previous) => !previous)}
              >
                Write
              </button>
            ) : null}
            {docked && !mine ? (
              <Link to="/journals?mine=1" className={`${QUIET_BUTTON_CLASS} no-underline`}>
                Your journal
              </Link>
            ) : null}
          </div>
        </header>

        {deskOpen && docked ? (
          <JournalDesk onPosted={() => setDeskOpen(false)} onDiscard={() => setDeskOpen(false)} />
        ) : null}

        {body()}
      </div>
    </div>
  );
}

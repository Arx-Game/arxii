/**
 * The Reading Room's Search (#3941) — the finding options, and the index under them.
 *
 * Not a mode and not a page: it drops down beside Write, over the stream, and
 * closing it always puts the reader back where they were. The grid of dates and
 * titles lives here and nowhere else — the stream itself is never a table — and
 * a row in it closes the panel and opens that entry in the stream.
 *
 * "About someone" and "Tags" are read off the rows the page already has rather
 * than from an endpoint of their own: they are a way into what is in front of
 * you, not a catalogue of everything ever written.
 */
import { useEffect, useMemo, useRef, useState } from 'react';

import { useDebouncedValue } from '@/hooks/useDebouncedValue';
import { cn } from '@/lib/utils';

import type { JournalEntryListFilters, JournalEntrySummary } from '../api';
import { formatPostingDate } from '../dates';
import { subjectsOf, tagsOf } from '../rows';

export interface SearchPanelProps {
  open: boolean;
  filters: JournalEntryListFilters;
  onFiltersChange: (filters: JournalEntryListFilters) => void;
  /** The page of entries the stream is currently showing. */
  rows: JournalEntrySummary[];
  onOpenEntry: (id: number) => void;
  isStaff: boolean;
  sinceVisitCount: number;
  /** Everything the current filters match; defaults to what is on this page. */
  totalCount?: number;
}

/** The five ways to narrow the stream. Exactly one holds at a time. */
type Scope = 'newest' | 'since_visit' | 'introductions' | 'post_mortem' | 'black_only';

const GROUP_HEAD_CLASS =
  'jr-sans m-0 text-[.6875rem] font-semibold uppercase tracking-[.14em] text-muted-foreground';

const OPTION_CLASS =
  'jr-sans cursor-pointer border-0 bg-transparent p-0 text-left text-[.875rem] text-foreground ' +
  'hover:underline';

const CELL_CLASS = 'border-b px-[.6rem] py-2 align-top';

function currentScope(filters: JournalEntryListFilters): Scope {
  if (filters.since_visit) return 'since_visit';
  if (filters.kind === 'introductions') return 'introductions';
  if (filters.post_mortem) return 'post_mortem';
  if (filters.black_only) return 'black_only';
  return 'newest';
}

/** An option with the number of things behind it, e.g. `Post mortems · 3`. */
function OptionCount({ count }: { count: number }) {
  if (count <= 0) return null;
  return (
    <>
      {' · '}
      <span className="jr-sans text-muted-foreground">{count}</span>
    </>
  );
}

export function SearchPanel({
  open,
  filters,
  onFiltersChange,
  rows,
  onOpenEntry,
  isStaff,
  sinceVisitCount,
  totalCount,
}: SearchPanelProps) {
  const [writerTerm, setWriterTerm] = useState(filters.writer ?? '');
  const debouncedWriter = useDebouncedValue(writerTerm, 300);
  const scope = currentScope(filters);
  const subjects = useMemo(() => subjectsOf(rows), [rows]);
  const tags = useMemo(() => tagsOf(rows), [rows]);

  // The debounce fires 300ms after the reader stops typing, by which time
  // `filters`/`onFiltersChange` may be newer objects than the ones that render
  // captured. The ref keeps the effect's dependency list down to the one thing
  // that should actually trigger it: the settled term.
  const latest = useRef({ filters, onFiltersChange });
  useEffect(() => {
    latest.current = { filters, onFiltersChange };
  });
  useEffect(() => {
    const applied = latest.current.filters.writer ?? '';
    if (debouncedWriter === applied) return;
    latest.current.onFiltersChange({
      ...latest.current.filters,
      writer: debouncedWriter || undefined,
    });
  }, [debouncedWriter]);

  function setScope(next: Scope) {
    onFiltersChange({
      ...filters,
      since_visit: next === 'since_visit' ? 1 : undefined,
      kind: next === 'introductions' ? 'introductions' : undefined,
      post_mortem: next === 'post_mortem' ? 1 : undefined,
      black_only: next === 'black_only' ? 1 : undefined,
    });
  }

  function scopeProps(next: Scope) {
    return {
      type: 'button' as const,
      className: cn(OPTION_CLASS, scope === next && 'font-semibold text-primary'),
      'aria-current': scope === next ? ('true' as const) : undefined,
      onClick: () => setScope(next),
    };
  }

  // Closed, only the anchor `aria-controls` names is left standing: an index of
  // every row, kept in the document but hidden, would say each title twice to
  // anything reading the page by text rather than by role.
  if (!open) return <div id="journal-search" hidden />;

  return (
    <div
      id="journal-search"
      className="mb-4 grid gap-x-8 gap-y-5 border-b pb-6 pt-5 sm:grid-cols-2 lg:grid-cols-4"
    >
      <div className="grid content-start gap-[.35rem]">
        <h4 className={GROUP_HEAD_CLASS}>Find a writer</h4>
        <input
          type="search"
          aria-label="Find a writer"
          placeholder="Name of a character"
          value={writerTerm}
          onChange={(event) => setWriterTerm(event.target.value)}
          className="jr-sans w-full rounded-[2px] border bg-card px-[.6rem] py-[.4rem] text-foreground"
        />
      </div>

      <div className="grid content-start gap-[.35rem]">
        <h4 className={GROUP_HEAD_CLASS}>Show</h4>
        <ul className="m-0 grid list-none gap-[.2rem] p-0">
          <li>
            <button {...scopeProps('newest')}>Newest</button>
          </li>
          <li>
            <button {...scopeProps('since_visit')}>
              Since your last visit
              <OptionCount count={sinceVisitCount} />
            </button>
          </li>
          <li>
            <button {...scopeProps('introductions')}>Introductions</button>
          </li>
          <li>
            <button {...scopeProps('post_mortem')}>Post mortems</button>
          </li>
          {isStaff ? (
            <li>
              <button {...scopeProps('black_only')}>Black journals only</button>
            </li>
          ) : null}
        </ul>
      </div>

      <div className="grid content-start gap-[.35rem]">
        <h4 className={GROUP_HEAD_CLASS}>About someone</h4>
        <ul className="m-0 grid list-none gap-[.2rem] p-0">
          {subjects.map((subject) => (
            <li key={subject.id}>
              <button
                type="button"
                className={cn(
                  OPTION_CLASS,
                  filters.about === subject.id && 'font-semibold text-primary'
                )}
                onClick={() => onFiltersChange({ ...filters, about: subject.id })}
              >
                {subject.name}
                <OptionCount count={subject.count} />
              </button>
            </li>
          ))}
        </ul>
      </div>

      <div className="grid content-start gap-[.35rem]">
        <h4 className={GROUP_HEAD_CLASS}>Tags</h4>
        <ul className="m-0 grid list-none gap-[.2rem] p-0">
          {tags.map((tag) => (
            <li key={tag}>
              <button
                type="button"
                className={cn(OPTION_CLASS, filters.tag === tag && 'font-semibold text-primary')}
                onClick={() => onFiltersChange({ ...filters, tag })}
              >
                {tag}
              </button>
            </li>
          ))}
        </ul>
      </div>

      <div className="overflow-x-auto sm:col-span-2 lg:col-span-4">
        <div className="jr-sans mb-[.4rem] text-[.6875rem] uppercase tracking-[.14em] text-muted-foreground">
          {rows.length} of {totalCount ?? rows.length}
        </div>
        <table className="jr-sans w-full border-collapse text-[.8125rem]">
          <thead>
            <tr>
              <th
                className={cn(
                  CELL_CLASS,
                  'whitespace-nowrap text-left text-[.6875rem] uppercase tracking-[.12em] text-muted-foreground'
                )}
              >
                Date
              </th>
              <th
                className={cn(
                  CELL_CLASS,
                  'text-left text-[.6875rem] uppercase tracking-[.12em] text-muted-foreground'
                )}
              >
                Writer
              </th>
              <th
                className={cn(
                  CELL_CLASS,
                  'text-left text-[.6875rem] uppercase tracking-[.12em] text-muted-foreground'
                )}
              >
                Title
              </th>
              <th
                className={cn(
                  CELL_CLASS,
                  'text-left text-[.6875rem] uppercase tracking-[.12em] text-muted-foreground'
                )}
              >
                About
              </th>
              <th
                className={cn(
                  CELL_CLASS,
                  'text-right text-[.6875rem] uppercase tracking-[.12em] text-muted-foreground'
                )}
              >
                Replies
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr
                key={row.id}
                onClick={() => onOpenEntry(row.id)}
                className={cn('cursor-pointer', !row.is_public && !row.revealed_at && 'jr-black')}
              >
                <td className={cn(CELL_CLASS, 'whitespace-nowrap')}>
                  {formatPostingDate(row.created_at)}
                </td>
                <td className={CELL_CLASS}>{row.author_name}</td>
                <td className={cn(CELL_CLASS, 'font-body text-[1.05rem]')}>
                  <button
                    type="button"
                    className="cursor-pointer border-0 bg-transparent p-0 text-left font-body text-[1.05rem] text-inherit hover:underline"
                    onClick={(event) => {
                      event.stopPropagation();
                      onOpenEntry(row.id);
                    }}
                  >
                    {row.revealed_at ? '◐ ' : null}
                    {row.title}
                  </button>
                </td>
                <td className={CELL_CLASS}>{row.about_name ?? '-'}</td>
                <td className={cn(CELL_CLASS, 'text-right')}>{row.response_count || '-'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

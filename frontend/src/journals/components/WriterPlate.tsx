/**
 * One writer's journal (#3941) — the night plate at the head of their stream,
 * and the three ways to cut it.
 *
 * The plate is painted in night literals in both light and dark mode, the same
 * argument the Reference Sheet's plate makes: a cover is the same object
 * whichever way the reader has the lights.
 *
 * The About filter is the relationship journal — everything this writer has
 * written about one person — and "Written about them" is its reverse, one
 * click away rather than a second page to find.
 */
import type { AboutSubject } from '../rows';
import { PillButton } from './Pill';

/** Which slice of a writer's journal is being read. */
export type WriterFilter =
  | { kind: 'all' }
  | { kind: 'about'; aboutId: number }
  | { kind: 'reverse' };

export interface WriterPlateProps {
  /** CharacterSheet id of the writer. */
  writerId: number;
  /** Their name, or null before any of their entries have arrived. */
  name: string | null;
  /** Their entry total; `black` is null unless the page holds the whole journal. */
  counts: { entries: number; black: number | null };
  /** Who this page of their entries is about. */
  subjects: AboutSubject[];
  filter: WriterFilter;
  onFilter: (filter: WriterFilter) => void;
  /** The reverse cut's total — entries by anyone about this writer — or undefined before it loads. */
  reverseCount?: number;
}

function isSameFilter(a: WriterFilter, b: WriterFilter): boolean {
  if (a.kind !== b.kind) return false;
  if (a.kind === 'about' && b.kind === 'about') return a.aboutId === b.aboutId;
  return true;
}

export function WriterPlate({
  writerId,
  name,
  counts,
  subjects,
  filter,
  onFilter,
  reverseCount,
}: WriterPlateProps) {
  return (
    <div data-writer-id={writerId}>
      <div className="jr-plate grid gap-2 p-[clamp(1.25rem,4vw,2.5rem)]">
        <div className="jr-sans jr-plate-soft text-[.6875rem] uppercase tracking-[.14em]">
          Journal of
        </div>
        <h1 className="jr-plate-strong m-0 font-display text-[clamp(1.6rem,4vw,2.4rem)] font-semibold tracking-[.04em]">
          {name ?? 'No entries yet'}
        </h1>
        <div className="jr-sans jr-plate-soft text-[.875rem]">
          <b className="jr-plate-strong font-semibold">{counts.entries}</b> entries
          {counts.black !== null && counts.black > 0 ? (
            <>
              {' · '}
              <b className="jr-plate-strong font-semibold">{counts.black}</b> black
            </>
          ) : null}
        </div>
      </div>

      <div className="flex flex-wrap gap-2 py-4">
        <PillButton
          pressed={isSameFilter(filter, { kind: 'all' })}
          onClick={() => onFilter({ kind: 'all' })}
        >
          All
        </PillButton>
        {subjects.map((subject) => (
          <PillButton
            key={subject.id}
            pressed={isSameFilter(filter, { kind: 'about', aboutId: subject.id })}
            onClick={() => onFilter({ kind: 'about', aboutId: subject.id })}
          >
            About {subject.name} · {subject.count}
          </PillButton>
        ))}
        <PillButton
          pressed={isSameFilter(filter, { kind: 'reverse' })}
          onClick={() => onFilter({ kind: 'reverse' })}
        >
          Written about them{reverseCount != null && reverseCount > 0 ? ` · ${reverseCount}` : ''}
        </PillButton>
      </div>
    </div>
  );
}

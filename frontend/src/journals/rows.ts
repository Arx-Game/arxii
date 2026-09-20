/**
 * What a page of entries says about itself (#3941).
 *
 * Search's "About someone" list and a writer's About filters are the same
 * question asked in two places — who the entries in front of the reader are
 * about — so the answer is derived once, here, from the rows the page already
 * holds. No endpoint: this is a way into what is on the page, not a catalogue.
 */
import type { JournalEntrySummary } from './api';

/** One character the current rows are about, with how many of them are. */
export interface AboutSubject {
  /** CharacterSheet id. */
  id: number;
  name: string;
  count: number;
}

/** Who these entries are about, most-written-about first. */
export function subjectsOf(rows: JournalEntrySummary[]): AboutSubject[] {
  const found = new Map<number, AboutSubject>();
  for (const row of rows) {
    if (row.about === null || !row.about_name) continue;
    const seen = found.get(row.about);
    if (seen) {
      seen.count += 1;
      continue;
    }
    found.set(row.about, { id: row.about, name: row.about_name, count: 1 });
  }
  return [...found.values()].sort((a, b) => b.count - a.count);
}

/** Every tag worn by these entries, in the order they first appear. */
export function tagsOf(rows: JournalEntrySummary[]): string[] {
  const names = new Set<string>();
  for (const row of rows) {
    for (const tag of row.tags) names.add(tag.name);
  }
  return [...names];
}

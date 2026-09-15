import type { FeedNote } from '@/hooks/types';

/** One row of a reader's column: an interaction-bearing item, or a typed note. */
export type FeedRow<T> = { type: 'item'; item: T } | { type: 'note'; note: FeedNote };

/**
 * Sort an item list and the session's notes into one column by time (#3856).
 *
 * Interaction timestamps come from the server (ISO-8601, sometimes without
 * milliseconds) and note timestamps from the client's clock at receipt, so the
 * comparison is on parsed time rather than on the strings the readers use
 * among themselves. A timestamp that will not parse sorts last, never out.
 * The sort is stable: items keep their given order on a tie and precede a note
 * that shares its instant, since the note (a look, an error) answers something
 * the player did after reading what was already there.
 */
export function interleaveNotes<T extends { timestamp: string }>(
  items: readonly T[],
  notes: readonly FeedNote[]
): FeedRow<T>[] {
  const rows: FeedRow<T>[] = [
    ...items.map((item): FeedRow<T> => ({ type: 'item', item })),
    ...notes.map((note): FeedRow<T> => ({ type: 'note', note })),
  ];
  return rows.sort((a, b) => feedTime(a) - feedTime(b));
}

function feedTime<T extends { timestamp: string }>(row: FeedRow<T>): number {
  const parsed = Date.parse(row.type === 'note' ? row.note.timestamp : row.item.timestamp);
  return Number.isFinite(parsed) ? parsed : Number.POSITIVE_INFINITY;
}

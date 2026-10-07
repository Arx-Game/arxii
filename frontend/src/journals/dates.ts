/**
 * The posting date a journal entry carries (#3941).
 *
 * An entry has an IC date (when the character wrote it, in the world's own
 * calendar) and a posting date (when the player posted it). The IC one arrives
 * already spelled in the game's calendar as `ic_timestamp_display` (#4185), so
 * only the posting date is formatted here.
 *
 * It formats in UTC: a floating local timezone would make the same entry read
 * as two different days for two readers of the same stream.
 */

const POSTING_FORMAT = new Intl.DateTimeFormat('en-GB', {
  day: 'numeric',
  month: 'short',
  year: 'numeric',
  timeZone: 'UTC',
});

/**
 * `17 Sep 2026` — the posting date, abbreviated.
 *
 * CLDR abbreviates September to "Sept" in `en-GB`, which is the only
 * four-letter month and makes a column of dates ragged; every abbreviation is
 * cut to three letters so the set stays even.
 */
export function formatPostingDate(iso: string): string {
  return POSTING_FORMAT.formatToParts(new Date(iso))
    .map((part) => (part.type === 'month' ? part.value.slice(0, 3) : part.value))
    .join('');
}

/**
 * The two dates a journal entry carries (#3941).
 *
 * An entry has an IC date (when the character wrote it, in the world's own
 * calendar) and a posting date (when the player posted it). The row shows the
 * IC one when there is one and flips to the posting date on a click, so both
 * spellings live here rather than in the row.
 *
 * Both format in UTC. An IC year can be three digits or fewer, which `Intl`
 * handles; a floating local timezone would make the same entry read as two
 * different days for two readers of the same stream, which the IC calendar in
 * particular cannot afford.
 */

const IC_FORMAT = new Intl.DateTimeFormat('en-GB', {
  day: 'numeric',
  month: 'long',
  year: 'numeric',
  timeZone: 'UTC',
});

const POSTING_FORMAT = new Intl.DateTimeFormat('en-GB', {
  day: 'numeric',
  month: 'short',
  year: 'numeric',
  timeZone: 'UTC',
});

/** `22 September 1012` — the in-character date, spelled out. */
export function formatIcDate(iso: string): string {
  return IC_FORMAT.format(new Date(iso));
}

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

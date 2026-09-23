/**
 * Almanach de Catenys chrome copy (#3983 Task 7) — the fixed strings Task 8/9's
 * pages reference, kept out of markup so a copy change never touches JSX.
 */

/** A ladder row's `state` value, as the pages display it. */
export const STATES = {
  held: 'Held',
  unclaimed: 'Unclaimed',
  undefined: 'Undefined',
} as const;

export const REVIEW_NOTE = 'Houses will be reviewed by staff before approval';

export const DRAFT_NOTE = 'draft kept as you type';

export const DISTRICT = 'district';

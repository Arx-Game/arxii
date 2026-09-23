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

/** Founder Almanach (#3983 Plan B) — the CG-mounted `.bar` crumb (plates
 * F-I onward) and the Seat's Claim button label. */
export const FOUNDER_CRUMB = ['Character creation', 'Lineage', 'Define a house'];

export const CLAIM = 'Claim';

/** House Document (#3983 Task 9) chrome copy — plates S-III to S-VIII. */

/** `house.house_state`, as `HouseChapter`'s state toggle labels it. */
export const HOUSE_STATES = {
  standing: 'Standing',
  in_exile: 'In exile',
  extinct: 'Extinct',
  gentry: 'Gentry',
} as const;

export const GENTRY_LUXEN_ONLY = 'Luxen only';

export const PUBLISH_STATUS = {
  draft: 'draft',
  published: 'published',
} as const;

export const DASH = '—';

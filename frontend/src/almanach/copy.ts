/**
 * Almanach de Catenys chrome copy (#3983 Task 7) — the fixed strings Task 8/9's
 * pages reference, kept out of markup so a copy change never touches JSX.
 */

/** A ladder row's `state` value, as the pages display it. */
export const STATES = {
  held: 'Held',
  unclaimed: 'Unclaimed',
  undefined: 'Undefined',
  // #4983: a dormant title with a charter and no land; an unnamed slot in open country.
  titular: 'Titular',
  potential: 'Potential',
} as const;

/** The faces of a title a reader is shown. Holdings are the rungs beneath it, the
 * ones its house holds directly and the ones its vassals hold (#5069, owner's words:
 * "these are the baronies under your family control in this chain, and these are
 * the baronies under your vassals"); the charter is what it held once (#4983). A
 * county's own land is its hinterland; a barony's or county's grid businesses are
 * its developments. Short words, never sentences. */
export const SECTIONS = {
  holdings: 'Holdings',
  held: 'Held',
  vassals: 'Vassals',
  hinterland: 'Hinterland',
  developments: 'Developments',
  // #5080: the regional events over the land, a blight, a war, a famine.
  events: 'Events',
  historical_charter: 'Historical Charter',
} as const;

export const REVIEW_NOTE = 'Houses will be reviewed by staff before approval';

export const DISTRICT = 'district';

/** Founder Almanach (#3983 Plan B) — the CG-mounted `.bar` crumb (plates
 * F-I onward) and the Seat's Claim button label. */
export const FOUNDER_CRUMB = ['Character creation', 'Lineage', 'Define a house'];

export const CLAIM = 'Claim';

/** "House <name>" for a heading, without doubling the word when the name
 * already carries it: the seed families are named "House Veyrane PLACEHOLDER"
 * and a staff member typed "House Katta" into Create Family (#4549). */
export function houseHeading(name: string): string {
  const trimmed = name.trim();
  return /^house\b/i.test(trimmed) ? trimmed : `House ${trimmed}`;
}

/** House Document (#3983 Task 9) chrome copy — plates S-III to S-VIII. */

/** `house.house_state`, as `HouseChapter`'s state toggle labels it. */
export const HOUSE_STATES = {
  standing: 'Active',
  in_exile: 'In exile',
  extinct: 'Extinct',
  gentry: 'Gentry',
} as const;

export const GENTRY_LUXEN_ONLY = 'Luxen only';

/** A realm's particles as the house page shows them: born, then taken-in ("aza / azas"). */
export const particlePair = (born: string, takenIn: string) =>
  takenIn && takenIn !== born ? `${born} / ${takenIn}` : born;

/** The record rail's links off a house page, named for where they go. */
export const houseOrgPage = (houseName: string) => `${houseName} org page`;
export const houseFamilyPage = (houseName: string) => `${houseName} family page`;

export const PUBLISH_STATUS = {
  draft: 'draft',
  published: 'published',
} as const;

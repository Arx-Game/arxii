/**
 * How staff surfaces show a kinsperson (#4239). Tier is numbered up the code
 * ladder and spelled long after the name; players never see it. Death and
 * absence are a mark after the name in the muted color, never a strikethrough.
 */
import type { AlmanachPersonRow } from '../types';

export const TIER_LABELS: Record<string, string> = {
  name_only: 'Offscreen Reference',
  functionary: 'Functionary NPC',
  standing: 'Standing NPC',
  sheeted: 'Sheeted NPC',
  pc: 'Player Character',
};

export const TIER_NUMBERS: Record<string, number | null> = {
  name_only: 0,
  functionary: 1,
  standing: 2,
  sheeted: 3,
  pc: null,
};

/** The four NPC tiers a person page's seg offers, in rising order. */
export const NPC_TIERS = ['name_only', 'functionary', 'standing', 'sheeted'] as const;

/** "(Standing NPC)" after a name on a staff page; "" for a PC, whose sheet is the link. */
export function tierMark(tier: string): string {
  if (tier === 'pc') return '';
  const label = TIER_LABELS[tier];
  return label ? `(${label})` : '';
}

/** "(RIP)" or "(Missing)" after a name; "" for the living. */
export function statusMark(status: AlmanachPersonRow['status'] | string): string {
  if (status === 'rip') return '(RIP)';
  if (status === 'missing') return '(Missing)';
  return '';
}

export function statusFromFlags(isDeceased: boolean, isMissing: boolean): string {
  if (isDeceased) return 'rip';
  if (isMissing) return 'missing';
  return 'alive';
}

export const personUrl = (id: number) => `/staff/almanach/people/${id}`;
export const titleUrl = (id: number) => `/staff/almanach/titles/${id}`;
export const houseUrl = (id: number) => `/staff/almanach/houses/${id}`;
export const familyUrl = (id: number) => `/staff/almanach/families/${id}`;
export const orgUrl = (id: number) => `/orgs/${id}`;

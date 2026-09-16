/**
 * Deity Editor shapes (#3780). The list, page and line types mirror the generated schema;
 * the dashboard tabs are the staff endpoints' own row shapes (`world.worship.staff_serializers`).
 */

import type { components } from '@/generated/api';

export type StaffBeingList = components['schemas']['StaffBeingList'];
export type StaffBeingPage = components['schemas']['StaffBeingPage'];
export type StaffBeingPageRequest = components['schemas']['StaffBeingPageRequest'];
export type ResonanceLine = components['schemas']['ResonanceLine'];
export type FeastDayLine = components['schemas']['FeastDayLine'];
export type RelationshipLine = components['schemas']['RelationshipLine'];

export type Visibility = 'public' | 'obscure' | 'secret';

export interface Ref {
  id: number;
  name: string;
}

export interface EditorOptions {
  traditions: Ref[];
  resonances: Ref[];
  facets: Ref[];
  tarot_cards: Ref[];
  organizations: Ref[];
  beings: Ref[];
}

export interface ActivityRow {
  when: string;
  text: string;
  note: string;
}

export interface Overview {
  resonance_pool: number;
  lifetime_worship: number;
  most_devoted_name: string | null;
  most_devoted_favor: number | null;
  site_count: number;
  recent_activity: ActivityRow[];
}

export interface ContributorRow {
  character_name: string;
  amount: number;
  reason: string;
  when: string;
}

export interface OfferingRow {
  item_name: string;
  offered_by: string;
  item_value: number;
  amount: number | null;
  ceremony_id: number;
  when: string | null;
}

export interface DevoteeRow {
  rank: number;
  character_name: string;
  favor: number;
  lifetime_favor: number;
  valence: string | null;
}

export interface WorshipTab {
  contributors: ContributorRow[];
  offerings: OfferingRow[];
  most_devoted: DevoteeRow[];
}

export interface SiteRow {
  kind: 'temple' | 'shrine';
  name: string;
  place: string;
  consecration_points: number;
  tier_name: string;
  bonus_percent: number;
  founder_name: string | null;
}

export interface StaffPrayer {
  id: number;
  character_sheet: number;
  character_name: string;
  text: string;
  devotion_granted: number;
  dire_straits: string;
  answered: boolean;
  place: string;
  prayed_at: string;
}

export interface StaffVision {
  id: number;
  recipient: number;
  recipient_name: string;
  body: string;
  reveal_source: boolean;
  prayer: number | null;
  clue: number | null;
  episode: number | null;
  resonance_spent: number;
  sent_by_name: string;
  sent_at: string;
}

export interface RelicRow {
  id: number;
  item_instance: number;
  item_name: string;
  lore: string;
  created_at: string;
}

export interface CodexRow {
  id: number;
  name: string;
  is_public: boolean;
  relation: string;
  organizations: string[];
  clues: string[];
}

/** The subset of a roster entry the Send-vision recipient picker reads. */
export interface RosterCharacterRef {
  id: number;
  character: { id: number; name: string };
}

/** A relationship line as the page reads it back: the other being's name rides along. */
export interface RelationshipLineWithName extends RelationshipLine {
  other_being_name?: string;
}

/** A resonance line as the page reads it back. */
export interface ResonanceLineWithName extends ResonanceLine {
  resonance_name?: string;
}

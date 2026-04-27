/**
 * Narrative TypeScript types
 *
 * Re-exports from frontend/src/generated/api.d.ts with local aliases,
 * plus hand-defined Gemit types (not yet in the generated schema).
 */

import type { components } from '@/generated/api';

export type NarrativeMessage = components['schemas']['NarrativeMessage'];
export type NarrativeMessageDelivery = components['schemas']['NarrativeMessageDelivery'];
export type NarrativeCategory = components['schemas']['NarrativeMessageCategoryEnum'];

export interface MyMessagesQueryParams {
  category?: NarrativeCategory;
  acknowledged?: boolean;
  page?: number;
}

export interface PaginatedDeliveries {
  count: number;
  next: string | null;
  previous: string | null;
  results: NarrativeMessageDelivery[];
}

// ---------------------------------------------------------------------------
// Gemit — hand-defined from GemitSerializer in world/narrative/serializers.py.
// Not yet in the generated api.d.ts schema.
// ---------------------------------------------------------------------------

export interface Gemit {
  id: number;
  body: string;
  sender_account: number | null;
  related_era: number | null;
  related_story: number | null;
  sent_at: string;
}

export interface BroadcastGemitBody {
  body: string;
  related_era?: number | null;
  related_story?: number | null;
}

export interface GemitListParams {
  related_era?: number;
  related_story?: number;
  page?: number;
}

export interface PaginatedGemits {
  count: number;
  next: string | null;
  previous: string | null;
  results: Gemit[];
}

// ---------------------------------------------------------------------------
// UserStoryMute — hand-defined from UserStoryMuteSerializer in
// world/narrative/serializers.py. Fields: id, story, muted_at.
// Not yet in the generated api.d.ts schema.
// ---------------------------------------------------------------------------

export interface UserStoryMute {
  id: number;
  /** PK of the related Story. */
  story: number;
  muted_at: string;
}

export interface UserStoryMuteCreateBody {
  story: number;
}

export interface PaginatedMutes {
  count: number;
  next: string | null;
  previous: string | null;
  results: UserStoryMute[];
}

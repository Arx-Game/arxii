/**
 * Narrative TypeScript types
 *
 * Re-exports from frontend/src/generated/api.d.ts with local aliases.
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

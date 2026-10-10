/**
 * Sheet update requests (#2631) — generated-type re-exports.
 *
 * TableUpdateRequestViewSet (/api/gm/table-update-requests/) and the
 * character-sheets profile-text-versions timeline endpoint.
 */

import type { components } from '@/generated/api';

export type TableUpdateRequest = components['schemas']['TableUpdateRequest'];
export type PaginatedTableUpdateRequests = components['schemas']['PaginatedTableUpdateRequestList'];
export type ProfileTextVersion = components['schemas']['ProfileTextVersion'];
export type GMTableMembership = components['schemas']['GMTableMembership'];

export const REQUEST_KINDS = {
  PROFILE_TEXT: 'profile_text',
  DISTINCTION_CHANGE: 'distinction_change',
} as const;

export const REQUEST_STATUSES = {
  PENDING: 'pending',
  APPROVED: 'approved',
  REJECTED: 'rejected',
  WITHDRAWN: 'withdrawn',
  COMPLETED: 'completed',
} as const;

export const PROFILE_TEXT_FIELDS = [
  { value: 'background', label: 'Background' },
  { value: 'never_do', label: 'What would you never do?' },
  { value: 'protect', label: 'What would you protect at all costs?' },
  { value: 'fear', label: 'What are you deathly afraid of?' },
] as const;

/**
 * Every versioned prose field's heading in the history timeline (#3988 widened the
 * versioned set past the four a player may request).
 */
export const PROSE_FIELD_LABELS: Record<string, string> = {
  background: 'Background',
  never_do: 'What would you never do?',
  protect: 'What would you protect at all costs?',
  fear: 'What are you deathly afraid of?',
  concept: 'Concept',
  quote: 'Quote',
  obituary: 'Obituary',
  description: 'Physical description',
};

export const DISTINCTION_ACTIONS = {
  ADD: 'distinction_add',
  REMOVE: 'distinction_remove',
} as const;

export interface CreateUpdateRequestBody {
  membership: number;
  kind: string;
  reasoning: string;
  field?: string;
  proposed_text?: string;
  action?: string;
  distinction?: number;
  character_distinction?: number;
}

export interface SignoffBody {
  approve: boolean;
  notes?: string;
}

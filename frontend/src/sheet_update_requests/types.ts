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
  { value: 'personality', label: 'Personality' },
] as const;

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

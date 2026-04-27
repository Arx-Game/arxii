/**
 * Tables TypeScript types
 *
 * Re-exports from @/generated/api plus hand-defined extensions for
 * computed serializer fields (member_count, story_count, viewer_role)
 * that are returned by GMTableSerializer but not yet reflected in the
 * generated schema.
 */

import type { components } from '@/generated/api';

// ---------------------------------------------------------------------------
// Base generated types
// ---------------------------------------------------------------------------

export type GMTableBase = components['schemas']['GMTable'];
export type GMTableMembership = components['schemas']['GMTableMembership'];
export type GMTableStatus = components['schemas']['GMTableStatusEnum'];

// ---------------------------------------------------------------------------
// Viewer role enum — mirrors GMTableViewerRole TextChoices on the backend
// (world/gm/constants.py). The generated schema does not expose this enum
// as a named type because it is a SerializerMethodField, not a db column.
// ---------------------------------------------------------------------------

export type GMTableViewerRole = 'gm' | 'staff' | 'member' | 'guest' | 'none';

// ---------------------------------------------------------------------------
// Full GMTable — base type extended with computed serializer fields
// ---------------------------------------------------------------------------

export interface GMTable extends GMTableBase {
  /** Active membership count (left_at__isnull=True). */
  readonly member_count: number;
  /** Stories where primary_table = this table. */
  readonly story_count: number;
  /** Requesting user's role relative to this table. */
  readonly viewer_role: GMTableViewerRole;
}

// ---------------------------------------------------------------------------
// Request / write shapes
// ---------------------------------------------------------------------------

export interface GMTableCreateBody {
  gm: number;
  name: string;
  description?: string;
}

export interface GMTableUpdateBody {
  name?: string;
  description?: string;
}

export interface GMTableTransferBody {
  new_gm: number;
}

export interface GMTableMembershipCreateBody {
  table: number;
  persona: number;
}

// ---------------------------------------------------------------------------
// Paginated wrappers
// ---------------------------------------------------------------------------

export interface PaginatedTables {
  count: number;
  next: string | null;
  previous: string | null;
  results: GMTable[];
}

export interface PaginatedMemberships {
  count: number;
  next: string | null;
  previous: string | null;
  results: GMTableMembership[];
}

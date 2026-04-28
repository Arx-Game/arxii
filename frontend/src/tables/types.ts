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

// ---------------------------------------------------------------------------
// Bulletin board types (Wave 10 backend; Wave 11 frontend)
// These types are hand-defined because the generated schema does not yet
// reflect the TableBulletinPost / TableBulletinReply serializer shapes.
// ---------------------------------------------------------------------------

/**
 * A single reply on a bulletin post.
 * Mirrors TableBulletinReplySerializer fields.
 */
export interface TableBulletinReply {
  readonly id: number;
  readonly post: number;
  /** PK of the author Persona. */
  readonly author_persona: number;
  /** Display name of the author (persona name). */
  readonly author_persona_name?: string;
  readonly body: string;
  readonly created_at: string;
}

/**
 * A bulletin post, including nested replies (from replies_cached Prefetch).
 * Mirrors TableBulletinPostSerializer fields.
 */
export interface TableBulletinPost {
  readonly id: number;
  /** PK of the owning GMTable. */
  readonly table: number;
  /** PK of the story this post is scoped to (null = table-wide). */
  readonly story: number | null;
  /** PK of the author Persona. */
  readonly author_persona: number;
  /** Display name of the author (persona name). */
  readonly author_persona_name?: string;
  readonly title: string;
  readonly body: string;
  readonly allow_replies: boolean;
  readonly created_at: string;
  readonly updated_at: string;
  /** Nested replies from replies_cached Prefetch. */
  readonly replies: TableBulletinReply[];
}

export interface PaginatedBulletinPosts {
  count: number;
  next: string | null;
  previous: string | null;
  results: TableBulletinPost[];
}

export interface PaginatedBulletinReplies {
  count: number;
  next: string | null;
  previous: string | null;
  results: TableBulletinReply[];
}

// ---------------------------------------------------------------------------
// Bulletin write shapes
// ---------------------------------------------------------------------------

export interface BulletinPostCreateBody {
  table: number;
  story?: number | null;
  /** PK of the author persona (Lead GM's persona at this table). */
  author_persona: number;
  title: string;
  body: string;
  allow_replies?: boolean;
}

export interface BulletinPostUpdateBody {
  title?: string;
  body?: string;
  allow_replies?: boolean;
}

export interface BulletinReplyCreateBody {
  post: number;
  /** PK of the author persona. */
  author_persona: number;
  body: string;
}

export interface BulletinReplyUpdateBody {
  body: string;
}

/**
 * Journals API functions (#2160).
 *
 * Thin `apiFetch` wrappers over `/api/journals/entries/`. Types are
 * hand-authored (not sourced from `@/generated/api`) because
 * `world.journals.views.JournalEntryViewSet` builds its responses from
 * plain `serializers.Serializer`/`ModelSerializer` calls inside each method
 * body rather than declaring `serializer_class` or `@extend_schema`
 * annotations — `drf-spectacular` can't introspect the response shape, so
 * every operation in `src/schema.json` for this app comes back "No response
 * body". Mirrors the same precedent as `frontend/src/stories/types.ts`'s
 * dashboard-endpoint types (see that app's CLAUDE.md "Common Gotchas").
 *
 * Keep these shapes in sync BY HAND with
 * `src/world/journals/serializers.py` / `constants.py` if the backend
 * changes.
 */

import { apiFetch } from '@/evennia_replacements/api';
import { readErrorDetail } from '@/lib/errors';

const ENTRIES_URL = '/api/journals/entries';

export type JournalResponseType = 'praise' | 'retort';

export interface JournalTag {
  id: number;
  name: string;
}

/** Shape returned by the list/mine feeds (`JournalEntryListSerializer`). */
export interface JournalEntrySummary {
  id: number;
  author: number;
  author_name: string;
  title: string;
  is_public: boolean;
  response_type: JournalResponseType | null;
  parent: number | null;
  created_at: string;
  edited_at: string | null;
  tags: JournalTag[];
  response_count: number;
}

/** Shape returned by retrieve/create/respond (`JournalEntryDetailSerializer`). */
export interface JournalEntryDetail {
  id: number;
  author: number;
  author_name: string;
  title: string;
  body: string;
  is_public: boolean;
  response_type: JournalResponseType | null;
  parent: number | null;
  created_at: string;
  edited_at: string | null;
  tags: JournalTag[];
  responses: JournalEntrySummary[];
}

export interface PaginatedJournalEntries {
  count: number;
  next: string | null;
  previous: string | null;
  results: JournalEntrySummary[];
}

export interface JournalEntryListFilters {
  /** CharacterSheet id — filter by author. */
  author?: number;
  /** Tag name — filter by tag. */
  tag?: string;
  page?: number;
  page_size?: number;
}

export interface CreateJournalEntryRequest {
  title: string;
  body: string;
  is_public: boolean;
  /** Freeform chip tags — never comma-split; each entry is one tag. */
  tags: string[];
}

export interface RespondToJournalRequest {
  title: string;
  body: string;
  response_type: JournalResponseType;
}

function jsonHeaders(): HeadersInit {
  return { 'Content-Type': 'application/json' };
}

function buildQuery(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined) search.set(key, String(value));
  }
  const qs = search.toString();
  return qs ? `?${qs}` : '';
}

/**
 * GET /api/journals/entries/
 *
 * Public feed. Supports `?author=` and `?tag=` filters, paginated
 * (page_size default 20, per `JournalEntryPagination`).
 */
export async function listJournalEntries(
  filters: JournalEntryListFilters = {}
): Promise<PaginatedJournalEntries> {
  const res = await apiFetch(`${ENTRIES_URL}/${buildQuery(filters)}`);
  if (!res.ok) {
    await readErrorDetail(res, 'Failed to load journal entries');
  }
  return res.json();
}

/**
 * GET /api/journals/entries/mine/
 *
 * The requesting character's own entries, including private ones.
 */
export async function listMyJournalEntries(
  params: { page?: number; page_size?: number } = {}
): Promise<PaginatedJournalEntries> {
  const res = await apiFetch(`${ENTRIES_URL}/mine/${buildQuery(params)}`);
  if (!res.ok) {
    await readErrorDetail(res, 'Failed to load your journal entries');
  }
  return res.json();
}

/** GET /api/journals/entries/{id}/ */
export async function getJournalEntry(id: number): Promise<JournalEntryDetail> {
  const res = await apiFetch(`${ENTRIES_URL}/${id}/`);
  if (!res.ok) {
    await readErrorDetail(res, 'Failed to load journal entry');
  }
  return res.json();
}

/** POST /api/journals/entries/ */
export async function createJournalEntry(
  body: CreateJournalEntryRequest
): Promise<JournalEntryDetail> {
  const res = await apiFetch(`${ENTRIES_URL}/`, {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    await readErrorDetail(res, 'Failed to post journal entry');
  }
  return res.json();
}

/** POST /api/journals/entries/{id}/respond/ */
export async function respondToJournal(
  id: number,
  body: RespondToJournalRequest
): Promise<JournalEntryDetail> {
  const res = await apiFetch(`${ENTRIES_URL}/${id}/respond/`, {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    await readErrorDetail(res, 'Failed to respond to journal entry');
  }
  return res.json();
}

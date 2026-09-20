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

export type JournalResponseType = 'praise' | 'retort' | 'condemn';

/**
 * Posthumous disposition (#3287) — the black journal afterlife. INHERIT falls through to
 * the author's sheet-level default; REVEAL/SEAL pin one entry regardless of that default.
 */
export type PosthumousOverride = 'inherit' | 'reveal' | 'seal';

/** The character-sheet-level default (`CharacterSheet.posthumous_journal_disposition`). */
export type PosthumousJournalDisposition = 'reveal' | 'seal';

/**
 * Who may Retort or Condemn this character's journal entries (#3941, ADR-0306). RIVALS
 * (default): only an active rival relationship, either direction. ANYONE: the writer has
 * opened the door. Praise and Nominate are never gated by this.
 */
export type RetortConsent = 'rivals' | 'anyone';

/**
 * What an entry is (`world.journals.constants.JournalKind`): an ordinary entry, or one
 * of the CG Introductions, which wear their own name in the row's band (#3941, #3621).
 */
export type JournalKind = 'entry' | 'first_journal' | 'application' | 'whispers';

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
  /**
   * The entry's full text. The feed sends it (`JournalEntryListSerializer.Meta.fields`)
   * so a collapsed row can show its first seven lines without a request of its own — the
   * list queryset has already narrowed to entries this viewer may read.
   */
  body: string;
  is_public: boolean;
  response_type: JournalResponseType | null;
  parent: number | null;
  created_at: string;
  edited_at: string | null;
  tags: JournalTag[];
  response_count: number;
  posthumous_override: PosthumousOverride;
  revealed_at: string | null;
  /** True once this entry has surfaced through an estate settlement. */
  is_posthumous: boolean;
  /** CharacterSheet id of the relationship-journal subject, if any (#3941). */
  about: number | null;
  about_name: string | null;
  /** The author's active Persona id, for routing to their public sheet (#3941). */
  author_persona_id: number | null;
  /** In-character timestamp the entry was written at, if the author has one (#3941). */
  ic_timestamp: string | null;
  /** Whether the viewer may Retort/Condemn this entry right now (#3941). */
  can_retort: boolean;
  /** True when the viewer's active character wrote this entry (#3941). */
  is_own: boolean;
  /**
   * What the entry is (#3941) — an ordinary entry, or one of the CG Introductions, whose
   * name the row wears in its band ("First Journal", "Application", "The Whispers").
   */
  kind: JournalKind;
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
  posthumous_override: PosthumousOverride;
  revealed_at: string | null;
  is_posthumous: boolean;
  about: number | null;
  about_name: string | null;
  author_persona_id: number | null;
  ic_timestamp: string | null;
  can_retort: boolean;
  is_own: boolean;
  /**
   * What the entry is (#3941) — an ordinary entry, or one of the CG Introductions, whose
   * name the row wears in its band ("First Journal", "Application", "The Whispers").
   */
  kind: JournalKind;
}

export interface PaginatedJournalEntries {
  count: number;
  next: string | null;
  previous: string | null;
  results: JournalEntrySummary[];
  /** Count of results newer than the viewer's last visit mark (#3941). */
  since_visit_count: number;
}

// A `type` alias (not `interface`) so it structurally satisfies `buildQuery`'s
// `Record<string, string | number | undefined>` parameter — TS only allows implicit
// index-signature assignability for object type literals, not declared interfaces.
export type JournalEntryListFilters = {
  /** CharacterSheet id — filter by author. */
  author?: number;
  /** Tag name — filter by tag. */
  tag?: string;
  /**
   * CharacterSheet id of a deceased character whose bequeathed corpus the caller is
   * browsing (#3287). Requires a `JournalBequestGrant` — otherwise returns empty, never
   * an error (so a probing id can't confirm a grant exists for someone else).
   */
  deceased?: number;
  /** Author name — Search's "writer" filter (#3941). */
  writer?: string;
  /** CharacterSheet id — entries about this character (#3941). */
  about?: number;
  /** A `JournalKind` value, or `"introductions"` for the three CG Introduction kinds (#3941). */
  kind?: string;
  /** 1 to restrict to entries revealed posthumously (#3941). */
  post_mortem?: 1;
  /** 1 to restrict to entries newer than the viewer's last visit mark (#3941). */
  since_visit?: 1;
  /** 1 to restrict to private ("black journal") entries (#3941). */
  black_only?: 1;
  /** 1 to stamp the viewer's visit mark as part of this request (#3941). */
  mark_visit?: 1;
  page?: number;
  page_size?: number;
};

export interface CreateJournalEntryRequest {
  title: string;
  body: string;
  is_public: boolean;
  /** Freeform chip tags — never comma-split; each entry is one tag. */
  tags: string[];
  /** Omit to leave the backend default (INHERIT) — only send when the author overrides it. */
  posthumous_override?: PosthumousOverride;
  /** CharacterSheet id this entry is about, or null for none (#3941). */
  about?: number | null;
}

export interface RespondToJournalRequest {
  title: string;
  body: string;
  response_type: JournalResponseType;
}

export interface EditJournalEntryRequest {
  title?: string;
  body?: string;
  posthumous_override?: PosthumousOverride;
  /** CharacterSheet id this entry is about, or null to clear it (#3941). */
  about?: number | null;
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
 * The Reading Room feed (#3941), paginated (page_size default 20, per
 * `JournalEntryPagination`). See `JournalEntryListFilters` for the full filter set
 * (`writer`, `about`, `kind`, `post_mortem`, `since_visit`, `black_only`, `mark_visit`,
 * plus the pre-existing `author`/`tag`/`deceased`). `?deceased=` switches to browsing a
 * bequeathed corpus (#3287) — empty unless the caller holds a grant for that sheet.
 * The response's `since_visit_count` reflects entries newer than the viewer's last visit
 * mark regardless of whether `?since_visit=1` was passed.
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

/** PATCH /api/journals/entries/{id}/ */
export async function editJournalEntry(
  id: number,
  body: EditJournalEntryRequest
): Promise<JournalEntryDetail> {
  const res = await apiFetch(`${ENTRIES_URL}/${id}/`, {
    method: 'PATCH',
    headers: jsonHeaders(),
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    await readErrorDetail(res, 'Failed to update journal entry');
  }
  return res.json();
}

/**
 * The caller's journal settings (#3941), formerly just the posthumous disposition:
 * their sheet-level posthumous default, who may Retort/Condemn them, and the weekly
 * posting-XP tracker (surfaced so the composer can show "N of M rewarded posts used").
 */
export interface JournalSettings {
  posthumous_journal_disposition: PosthumousJournalDisposition;
  retort_consent: RetortConsent;
  posts_this_week: number;
  rewarded_posts_per_week: number;
}

export interface PatchJournalSettingsRequest {
  disposition?: PosthumousJournalDisposition;
  retort_consent?: RetortConsent;
}

/** GET /api/journals/entries/disposition/ — the caller's journal settings (#3941, was #3287). */
export async function getJournalSettings(): Promise<JournalSettings> {
  const res = await apiFetch(`${ENTRIES_URL}/disposition/`);
  if (!res.ok) {
    await readErrorDetail(res, 'Failed to load journal settings');
  }
  return res.json();
}

/**
 * PATCH /api/journals/entries/disposition/ — update the caller's journal settings
 * (#3941, was #3287). Sends only the keys given, so a partial update (e.g. just
 * `retort_consent`) never clobbers the other setting.
 */
export async function patchJournalSettings(
  body: PatchJournalSettingsRequest
): Promise<JournalSettings> {
  const res = await apiFetch(`${ENTRIES_URL}/disposition/`, {
    method: 'PATCH',
    headers: jsonHeaders(),
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    await readErrorDetail(res, 'Failed to update journal settings');
  }
  return res.json();
}

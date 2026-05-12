/**
 * Rituals API functions
 *
 * Covers RitualViewSet (/api/magic/rituals/) and RitualPerformView
 * (/api/magic/rituals/perform/) from the Soul Tether backend (Phase 1).
 *
 * Also covers RitualSessionViewSet (/api/magic/rituals/sessions/) from the
 * Covenants Slice B backend (Phase 8).
 *
 * Uses apiFetch from @/evennia_replacements/api.
 */

import { apiFetch } from '@/evennia_replacements/api';
import type {
  PerformRitualRequest,
  PerformRitualResponse,
  PaginatedRitualList,
  Ritual,
} from './types';
import type { components } from '@/generated/api';

// ---------------------------------------------------------------------------
// Generated type aliases
// ---------------------------------------------------------------------------

export type RitualSessionList = components['schemas']['RitualSessionList'];
export type RitualSessionDetail = components['schemas']['RitualSessionDetail'];
// The create endpoint returns RitualSessionDetail (declared via @extend_schema
// on the view). Keep the legacy `RitualSessionDraft` name as an alias so
// callers that imported it continue to work — but resolve it to the detail
// shape so consumers see `.id` and other read fields.
export type RitualSessionDraft = components['schemas']['RitualSessionDetail'];
export type RitualSessionDraftRequest = components['schemas']['RitualSessionDraftRequest'];
export type RitualSessionAccept = components['schemas']['RitualSessionAccept'];
export type RitualSessionAcceptRequest = components['schemas']['RitualSessionAcceptRequest'];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function jsonHeaders(): HeadersInit {
  return { 'Content-Type': 'application/json' };
}

// ---------------------------------------------------------------------------
// URL constants
// ---------------------------------------------------------------------------

const RITUALS_URL = '/api/magic/rituals';
const SESSIONS_URL = '/api/magic/rituals/sessions';

// ---------------------------------------------------------------------------
// Ritual reads
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Anima ritual edit (PATCH)
// ---------------------------------------------------------------------------

export interface AnimaRitualPatchBody {
  name?: string;
  description?: string;
  narrative_prose?: string;
  /** FK pk for traits.Trait (stat) */
  stat_id?: number | null;
  /** FK pk for skills.Skill */
  skill_id?: number | null;
  /** FK pk for skills.Specialization */
  specialization_id?: number | null;
  /** FK pk for magic.Resonance */
  resonance_id?: number | null;
  /** FK pk for checks.CheckType */
  check_type_id?: number | null;
  target_difficulty?: number;
}

/**
 * PATCH /api/magic/rituals/{id}/
 *
 * Partially updates a player-authored anima ritual and its sidecar config.
 *
 * NOTE (Phase 9 gap): The backend RitualViewSet is currently ReadOnlyModelViewSet
 * and does not accept PATCH. This function will return a 405 until the backend
 * is upgraded to support partial updates. Flag for Phase 10.
 */
export async function patchRitual(id: number, body: AnimaRitualPatchBody): Promise<Ritual> {
  const res = await apiFetch(`${RITUALS_URL}/${id}/`, {
    method: 'PATCH',
    headers: jsonHeaders(),
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    let detail = 'Failed to update ritual';
    try {
      const data = (await res.json()) as { detail?: string };
      if (typeof data.detail === 'string' && data.detail.trim()) {
        detail = data.detail;
      }
    } catch {
      // body wasn't JSON; keep generic
    }
    throw new Error(detail);
  }

  return res.json() as Promise<Ritual>;
}

// ---------------------------------------------------------------------------
// Ritual reads
// ---------------------------------------------------------------------------

export async function getRituals(): Promise<PaginatedRitualList> {
  const res = await apiFetch(`${RITUALS_URL}/`);
  if (!res.ok) throw new Error('Failed to load rituals');
  return res.json() as Promise<PaginatedRitualList>;
}

export async function getRitual(id: number): Promise<Ritual> {
  const res = await apiFetch(`${RITUALS_URL}/${id}/`);
  if (!res.ok) throw new Error(`Failed to load ritual ${id}`);
  return res.json() as Promise<Ritual>;
}

// ---------------------------------------------------------------------------
// Ritual perform
// ---------------------------------------------------------------------------

/**
 * POST /api/magic/rituals/perform/
 * Dispatches a ritual with the supplied character sheet and kwargs.
 *
 * On error, parses the response body for a typed `detail` message from the backend
 * and throws it as an Error.message. Falls back to a generic message if the response
 * is not JSON or has no detail field.
 */
export async function performRitual(body: PerformRitualRequest): Promise<PerformRitualResponse> {
  const res = await apiFetch(`${RITUALS_URL}/perform/`, {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    let detail = 'Failed to perform ritual';
    try {
      const data = (await res.json()) as { detail?: string };
      if (typeof data.detail === 'string' && data.detail.trim()) {
        detail = data.detail;
      }
    } catch {
      // body wasn't JSON; keep generic
    }
    throw new Error(detail);
  }

  return res.json() as Promise<PerformRitualResponse>;
}

// ---------------------------------------------------------------------------
// RitualSession reads (Covenants Slice B)
// ---------------------------------------------------------------------------

/**
 * GET /api/magic/rituals/sessions/?as_invitee=me
 * Returns sessions where the current user is an invited participant.
 */
export async function fetchRitualSessionInbox(): Promise<RitualSessionList[]> {
  const res = await apiFetch(`${SESSIONS_URL}/?as_invitee=me`);
  if (!res.ok) throw new Error('Failed to load ritual session inbox');
  return res.json() as Promise<RitualSessionList[]>;
}

/**
 * GET /api/magic/rituals/sessions/?as_initiator=me
 * Returns sessions where the current user is the initiator.
 */
export async function fetchRitualSessionOutbox(): Promise<RitualSessionList[]> {
  const res = await apiFetch(`${SESSIONS_URL}/?as_initiator=me`);
  if (!res.ok) throw new Error('Failed to load ritual session outbox');
  return res.json() as Promise<RitualSessionList[]>;
}

/**
 * GET /api/magic/rituals/sessions/{id}/
 * Returns full session detail including all participants.
 */
export async function fetchRitualSessionDetail(id: number): Promise<RitualSessionDetail> {
  const res = await apiFetch(`${SESSIONS_URL}/${id}/`);
  if (!res.ok) throw new Error(`Failed to load ritual session ${id}`);
  return res.json() as Promise<RitualSessionDetail>;
}

// ---------------------------------------------------------------------------
// RitualSession writes (Covenants Slice B)
// ---------------------------------------------------------------------------

async function parseErrorDetail(res: Response, fallback: string): Promise<never> {
  let detail = fallback;
  try {
    const data = (await res.json()) as { detail?: string };
    if (typeof data.detail === 'string' && data.detail.trim()) {
      detail = data.detail;
    }
  } catch {
    // body wasn't JSON; keep generic
  }
  throw new Error(detail);
}

/**
 * POST /api/magic/rituals/sessions/
 * Draft a new ritual session as initiator.
 */
export async function draftRitualSession(
  body: RitualSessionDraftRequest
): Promise<RitualSessionDraft> {
  const res = await apiFetch(`${SESSIONS_URL}/`, {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify(body),
  });
  if (!res.ok) await parseErrorDetail(res, 'Failed to draft ritual session');
  return res.json() as Promise<RitualSessionDraft>;
}

/**
 * POST /api/magic/rituals/sessions/{id}/accept/
 * Accept an invitation, supplying optional participant_kwargs and references.
 */
export async function acceptRitualSession(
  id: number,
  body: RitualSessionAcceptRequest
): Promise<RitualSessionAccept> {
  const res = await apiFetch(`${SESSIONS_URL}/${id}/accept/`, {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify(body),
  });
  if (!res.ok) await parseErrorDetail(res, 'Failed to accept ritual session');
  return res.json() as Promise<RitualSessionAccept>;
}

/**
 * POST /api/magic/rituals/sessions/{id}/decline/
 * Decline an invitation. Returns 204 if the session was deleted entirely.
 */
export async function declineRitualSession(id: number): Promise<RitualSessionAccept | null> {
  const res = await apiFetch(`${SESSIONS_URL}/${id}/decline/`, {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify({}),
  });
  if (!res.ok) await parseErrorDetail(res, 'Failed to decline ritual session');
  // 204 → session was deleted; no body
  if (res.status === 204) return null;
  return res.json() as Promise<RitualSessionAccept>;
}

/**
 * POST /api/magic/rituals/sessions/{id}/fire/
 * Initiator fires the session once threshold is met.
 * Returns the updated RitualSessionList row (the session is closed after fire).
 */
export async function fireRitualSession(id: number): Promise<RitualSessionList> {
  const res = await apiFetch(`${SESSIONS_URL}/${id}/fire/`, {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify({}),
  });
  if (!res.ok) await parseErrorDetail(res, 'Failed to fire ritual session');
  return res.json() as Promise<RitualSessionList>;
}

/**
 * DELETE /api/magic/rituals/sessions/{id}/
 * Cancel a session (initiator-only). Returns 204.
 */
export async function cancelRitualSession(id: number): Promise<void> {
  const res = await apiFetch(`${SESSIONS_URL}/${id}/`, {
    method: 'DELETE',
  });
  if (!res.ok) await parseErrorDetail(res, 'Failed to cancel ritual session');
}

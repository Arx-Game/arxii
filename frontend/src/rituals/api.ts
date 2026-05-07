/**
 * Rituals API functions
 *
 * Covers RitualViewSet (/api/magic/rituals/) and RitualPerformView
 * (/api/magic/rituals/perform/) from the Soul Tether backend (Phase 1).
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

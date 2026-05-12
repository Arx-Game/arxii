/**
 * Covenants API functions
 *
 * Covers:
 *   - CovenantViewSet  (/api/covenants/covenants/)
 *   - CharacterCovenantRoleViewSet (/api/covenants/character-roles/)
 *     including engage/disengage custom actions (Phase 7)
 *
 * Uses apiFetch from @/evennia_replacements/api.
 */

import { apiFetch } from '@/evennia_replacements/api';
import type { components } from '@/generated/api';

// ---------------------------------------------------------------------------
// Generated type aliases
// ---------------------------------------------------------------------------

export type Covenant = components['schemas']['Covenant'];
export type CharacterCovenantRole = components['schemas']['CharacterCovenantRole'];
export type PaginatedCovenantList = components['schemas']['PaginatedCovenantList'];
export type PaginatedCharacterCovenantRoleList =
  components['schemas']['PaginatedCharacterCovenantRoleList'];

// ---------------------------------------------------------------------------
// URL constants
// ---------------------------------------------------------------------------

const COVENANTS_URL = '/api/covenants/covenants';
const CHARACTER_ROLES_URL = '/api/covenants/character-roles';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function jsonHeaders(): HeadersInit {
  return { 'Content-Type': 'application/json' };
}

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

// ---------------------------------------------------------------------------
// Covenant reads
// ---------------------------------------------------------------------------

export async function getCovenants(): Promise<PaginatedCovenantList> {
  const res = await apiFetch(`${COVENANTS_URL}/`);
  if (!res.ok) throw new Error('Failed to load covenants');
  return res.json() as Promise<PaginatedCovenantList>;
}

export async function getCovenant(id: number): Promise<Covenant> {
  const res = await apiFetch(`${COVENANTS_URL}/${id}/`);
  if (!res.ok) throw new Error(`Failed to load covenant ${id}`);
  return res.json() as Promise<Covenant>;
}

// ---------------------------------------------------------------------------
// CharacterCovenantRole reads
// ---------------------------------------------------------------------------

/**
 * GET /api/covenants/character-roles/?covenant={covenantId}
 * Returns all membership rows for the given covenant.
 */
export async function getCharacterRolesForCovenant(
  covenantId: number
): Promise<PaginatedCharacterCovenantRoleList> {
  const res = await apiFetch(`${CHARACTER_ROLES_URL}/?covenant=${covenantId}`);
  if (!res.ok) throw new Error(`Failed to load members for covenant ${covenantId}`);
  return res.json() as Promise<PaginatedCharacterCovenantRoleList>;
}

// ---------------------------------------------------------------------------
// Engage / disengage mutations
// ---------------------------------------------------------------------------

/**
 * POST /api/covenants/character-roles/{id}/engage/
 * Engage a covenant role. Returns the updated CharacterCovenantRole row.
 */
export async function engageMembership(id: number): Promise<CharacterCovenantRole> {
  const res = await apiFetch(`${CHARACTER_ROLES_URL}/${id}/engage/`, {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify({}),
  });
  if (!res.ok) await parseErrorDetail(res, 'Failed to engage covenant role');
  return res.json() as Promise<CharacterCovenantRole>;
}

/**
 * POST /api/covenants/character-roles/{id}/disengage/
 * Disengage a covenant role. Returns the updated CharacterCovenantRole row.
 */
export async function disengageMembership(id: number): Promise<CharacterCovenantRole> {
  const res = await apiFetch(`${CHARACTER_ROLES_URL}/${id}/disengage/`, {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify({}),
  });
  if (!res.ok) await parseErrorDetail(res, 'Failed to disengage covenant role');
  return res.json() as Promise<CharacterCovenantRole>;
}

/**
 * Achievements API client (#1522).
 *
 * Currently the earned-titles read for a character's Titles tab. Plain async fetchers —
 * React Query hooks live in queries.ts.
 */

import { apiFetch } from '@/evennia_replacements/api';
import type { components } from '@/generated/api';

export type PersonaTitle = components['schemas']['PersonaTitle'];

interface PaginatedTitles {
  results: PersonaTitle[];
}

/**
 * Fetch a persona's earned, displayable titles (newest first).
 * GET /api/achievements/persona-titles/?persona={id}
 *
 * Titles are scoped to the PERSONA that earned them, not the character sheet (#3466) — a
 * deed earned behind a mask titles the mask, never the sheet. `persona` is required by the
 * backend (400 if absent, since the endpoint has no pagination).
 *
 * The achievements API isn't globally paginated, so the list endpoint returns a bare array;
 * tolerate a paginated `{results}` shape too in case pagination is added later.
 */
export async function fetchPersonaTitles(personaId: number): Promise<PersonaTitle[]> {
  const res = await apiFetch(`/api/achievements/persona-titles/?persona=${personaId}`);
  if (!res.ok) throw new Error('Failed to load titles');
  const data = (await res.json()) as PersonaTitle[] | PaginatedTitles;
  return Array.isArray(data) ? data : data.results;
}

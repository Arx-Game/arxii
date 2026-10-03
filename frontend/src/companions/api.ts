/** Companion API functions (#672, #3294). */

import { apiFetch } from '@/evennia_replacements/api';
import type { CompanionArchetypeSummary, CompanionListResponse, CompanionSummary } from './types';

const BASE_URL = '/api/companions/companions';
const ARCHETYPES_URL = '/api/companions/companion-archetypes';

/** The viewer's own active character's bonded, active companions (each carrying
 * `is_present`, #3294 — whether it currently shares the actor's room). Self-scoped
 * server-side; an account with no active character gets an empty array. */
export async function fetchMyCompanions(): Promise<CompanionSummary[]> {
  const res = await apiFetch(`${BASE_URL}/`);
  if (!res.ok) {
    throw new Error('Failed to load companions');
  }
  const data = (await res.json()) as CompanionListResponse | CompanionSummary[];
  return Array.isArray(data) ? data : (data.results ?? []);
}

/** The authored catalog of bindable CompanionArchetype rows (#4091) — `GET
 * /api/companions/companion-archetypes/` (`CompanionArchetypeViewSet`, read-only,
 * unpaginated). Backs the Bind-as-companion archetype picker. */
export async function fetchCompanionArchetypes(): Promise<CompanionArchetypeSummary[]> {
  const res = await apiFetch(`${ARCHETYPES_URL}/`);
  if (!res.ok) {
    throw new Error('Failed to load companion archetypes');
  }
  return (await res.json()) as CompanionArchetypeSummary[];
}

/** Pose as a bonded, present companion (#3294) — `POST
 * /api/companions/companions/{id}/emote/`. Wraps `CompanionEmoteAction`; the server
 * re-validates ownership + room presence (`CompanionPresentPrerequisite`). */
export async function companionEmote(
  companionId: number,
  text: string,
  clientRequestId?: string
): Promise<void> {
  const res = await apiFetch(`${BASE_URL}/${companionId}/emote/`, {
    method: 'POST',
    body: JSON.stringify(clientRequestId ? { text, client_request_id: clientRequestId } : { text }),
  });
  if (!res.ok) {
    const data = (await res.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(data?.detail || 'Failed to emote as companion');
  }
}

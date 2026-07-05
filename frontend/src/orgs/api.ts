/**
 * Organizations API client (#1446) — family/covenant click-throughs on the character sheet.
 *
 * Reads `/api/societies/organizations/` filtered by name (iexact match server-side). Used to
 * resolve a character's family name to a same-named organization for a link target. Visibility
 * is members-only on the backend, so an empty result is normal — callers should render plain
 * text in that case, not an error.
 */

import { apiFetch } from '@/evennia_replacements/api';
import type { components } from '@/generated/api';

export type Organization = components['schemas']['Organization'];

interface PaginatedOrganizations {
  results: Organization[];
}

/**
 * Resolve an organization by exact (iexact) name.
 * GET /api/societies/organizations/?name={name}
 */
export async function fetchOrganizationByName(name: string): Promise<Organization | null> {
  const res = await apiFetch(`/api/societies/organizations/?name=${encodeURIComponent(name)}`);
  if (!res.ok) throw new Error('Failed to load organization');
  const data = (await res.json()) as PaginatedOrganizations;
  return data.results[0] ?? null;
}

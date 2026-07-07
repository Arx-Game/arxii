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
export type HouseDetail = components['schemas']['HouseDetail'];
export type PublicFeedItem = components['schemas']['PublicFeedItem'];

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

/**
 * Fetch a single organization by id, for the org detail stub page (#1446).
 * GET /api/societies/organizations/{id}/
 *
 * Members-only: the backend excludes non-member requesters, so a 404 here is
 * expected and normal — callers should treat query errors as "render the
 * not-yet-public placeholder," not a hard failure.
 */
export async function fetchOrganizationById(id: number): Promise<Organization> {
  const res = await apiFetch(`/api/societies/organizations/${id}/`);
  if (!res.ok) throw new Error('Failed to load organization');
  return (await res.json()) as Organization;
}

/**
 * Fetch the house feed (#1884): recent deeds + revealed scandals of the household.
 * GET /api/societies/organizations/{id}/feed/
 */
export async function fetchHouseFeed(id: number): Promise<PublicFeedItem[]> {
  const res = await apiFetch(`/api/societies/organizations/${id}/feed/`);
  if (!res.ok) throw new Error('Failed to load house feed');
  return (await res.json()) as PublicFeedItem[];
}

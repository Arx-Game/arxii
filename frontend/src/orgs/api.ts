/**
 * Organizations API client (#1446) — family/covenant click-throughs on the character sheet.
 *
 * Reads `/api/societies/organizations/` filtered by name (iexact match server-side). Used to
 * resolve a character's family name to a same-named organization for a link target. Visibility
 * is members-only on the backend, so an empty result is normal — callers should render plain
 * text in that case, not an error.
 */

import { apiFetch } from '@/evennia_replacements/api';
import { throwApiError } from '@/lib/errors';
import type { components } from '@/generated/api';

export type Organization = components['schemas']['Organization'];
export type HouseDetail = components['schemas']['HouseDetail'];
export type HouseStature = components['schemas']['HouseStature'];
export type OrgDossier = components['schemas']['OrgDossier'];
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
 * Fetch the match-review dossier (#2999): what a candidate house truly brings.
 * GET /api/societies/organizations/{id}/dossier/
 *
 * Readable by any authenticated player — reviewing RIVAL houses is the point.
 */
export async function fetchOrgDossier(id: number): Promise<OrgDossier> {
  const res = await apiFetch(`/api/societies/organizations/${id}/dossier/`);
  if (!res.ok) throw new Error('Failed to load dossier');
  return (await res.json()) as OrgDossier;
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

export type HouseCrisis = components['schemas']['HouseCrisis'];

/**
 * The administrator's judgment call on an open domain crisis (#2238).
 * POST /api/societies/organizations/{id}/crisis-option/
 */
export async function chooseCrisisOption(
  orgId: number,
  crisisId: number,
  optionId: number
): Promise<{ open_crises: HouseCrisis[] }> {
  const res = await apiFetch(`/api/societies/organizations/${orgId}/crisis-option/`, {
    method: 'POST',
    body: JSON.stringify({ crisis: crisisId, option: optionId }),
  });
  if (!res.ok) await throwApiError(res, 'Failed to act on the crisis');
  return res.json();
}

// ---------------------------------------------------------------------------
// Appeals to organizations (#3293)
//
// Hand-rolled types: the generated `components['schemas']` types above come
// from `pnpm generate:types` running against a live drf-spectacular schema,
// which this change doesn't regenerate. Swap these for the generated
// equivalents the next time that step runs.
// ---------------------------------------------------------------------------

export type OrgAppealState = 'open' | 'granted' | 'declined' | 'withdrawn';

export interface OrgAppealSignon {
  id: number;
  member_persona: number;
  member_persona_name: string;
  note: string;
  created_at: string;
}

export interface OrgAppeal {
  id: number;
  organization: number;
  organization_name: string;
  petitioner_persona: number;
  petitioner_persona_name: string;
  title: string;
  body: string;
  state: OrgAppealState;
  resolution_text: string;
  resolved_by_persona: number | null;
  resolved_by_persona_name: string;
  created_at: string;
  resolved_at: string | null;
  signons: OrgAppealSignon[];
}

interface PaginatedOrgAppeals {
  results: OrgAppeal[];
}

/** List appeals visible to the requester for one organization (#3293). */
export async function fetchOrgAppeals(orgId: number): Promise<OrgAppeal[]> {
  const res = await apiFetch(`/api/societies/appeals/?organization=${orgId}`);
  if (!res.ok) await throwApiError(res, 'Failed to load appeals');
  const data = (await res.json()) as PaginatedOrgAppeals;
  return data.results;
}

/** Lodge an appeal with an organization. POST /api/societies/appeals/ */
export async function lodgeOrgAppeal(
  orgId: number,
  title: string,
  body: string
): Promise<OrgAppeal> {
  const res = await apiFetch('/api/societies/appeals/', {
    method: 'POST',
    body: JSON.stringify({ organization: orgId, title, body }),
  });
  if (!res.ok) await throwApiError(res, 'Failed to lodge the appeal');
  return res.json();
}

/** Sign onto an open appeal. POST /api/societies/appeals/{id}/signon/ */
export async function signonOrgAppeal(appealId: number, note: string): Promise<OrgAppeal> {
  const res = await apiFetch(`/api/societies/appeals/${appealId}/signon/`, {
    method: 'POST',
    body: JSON.stringify({ note }),
  });
  if (!res.ok) await throwApiError(res, 'Failed to sign onto the appeal');
  return res.json();
}

/** Grant/decline an open appeal. POST /api/societies/appeals/{id}/resolve/ */
export async function resolveOrgAppeal(
  appealId: number,
  verdict: 'grant' | 'decline',
  answer: string
): Promise<OrgAppeal> {
  const res = await apiFetch(`/api/societies/appeals/${appealId}/resolve/`, {
    method: 'POST',
    body: JSON.stringify({ verdict, answer }),
  });
  if (!res.ok) await throwApiError(res, 'Failed to resolve the appeal');
  return res.json();
}

/** Withdraw your own open appeal. POST /api/societies/appeals/{id}/withdraw/ */
export async function withdrawOrgAppeal(appealId: number): Promise<OrgAppeal> {
  const res = await apiFetch(`/api/societies/appeals/${appealId}/withdraw/`, {
    method: 'POST',
  });
  if (!res.ok) await throwApiError(res, 'Failed to withdraw the appeal');
  return res.json();
}

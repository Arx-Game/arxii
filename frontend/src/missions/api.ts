/**
 * Mission Studio API fetch wrappers.
 *
 * Pure functions — pair with React Query hooks in queries.ts. Use the
 * shared `apiFetch` for cookie/CSRF and base-URL handling. All endpoints
 * are staff-only (IsAdminUser on the backend); player-facing surfaces
 * land in a future phase.
 */

import { apiFetch } from '@/evennia_replacements/api';
import type {
  MissionCategory,
  MissionGiver,
  MissionGiverOffering,
  MissionGiverStanding,
  MissionInstance,
  MissionNode,
  MissionOption,
  MissionOptionRoute,
  MissionOptionRouteCandidate,
  MissionOptionRouteReward,
  MissionTemplate,
  MissionTemplateDetail,
  MissionTemplateFilters,
  PaginatedResponse,
} from './types';

const BASE_URL = '/api/missions';

export class ApiValidationError extends Error {
  readonly fieldErrors: Record<string, unknown>;
  constructor(detail: unknown) {
    super('Validation error');
    this.name = 'ApiValidationError';
    this.fieldErrors =
      typeof detail === 'object' && detail !== null ? (detail as Record<string, unknown>) : {};
  }
}

/**
 * Recursively flatten a DRF error shape into a single readable string.
 *
 * DRF can return deeply nested error bodies (e.g. nested serializer errors,
 * list-of-object errors). This collapses them into a human-readable sentence.
 * Used by CreateMissionPage and StaffActionsCard to surface API errors inline.
 */
export function flattenErrorMessage(value: unknown): string {
  if (typeof value === 'string') return value;
  if (Array.isArray(value)) {
    const flat = value.map(flattenErrorMessage).filter(Boolean);
    return flat.length > 0 ? flat[0] : '';
  }
  if (value !== null && typeof value === 'object') {
    const parts: string[] = [];
    for (const [k, v] of Object.entries(value)) {
      const sub = flattenErrorMessage(v);
      if (sub) parts.push(`${k}: ${sub}`);
    }
    return parts.join('; ');
  }
  return String(value);
}

function buildQueryString(params: object): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue;
    search.append(key, String(value));
  }
  const s = search.toString();
  return s ? `?${s}` : '';
}

// ---------------------------------------------------------------------------
// MissionTemplate (D1)
// ---------------------------------------------------------------------------

export async function listMissionTemplates(
  filters: MissionTemplateFilters & { page?: number } = {}
): Promise<PaginatedResponse<MissionTemplate>> {
  const res = await apiFetch(`${BASE_URL}/templates/${buildQueryString(filters)}`);
  if (!res.ok) throw new Error('Failed to load mission templates');
  return res.json();
}

export async function getMissionTemplate(id: number): Promise<MissionTemplateDetail> {
  const res = await apiFetch(`${BASE_URL}/templates/${id}/`);
  if (!res.ok) throw new Error(`Failed to load template ${id}`);
  return res.json();
}

export async function patchMissionTemplate(
  id: number,
  body: Partial<MissionTemplate>
): Promise<MissionTemplate> {
  const res = await apiFetch(`${BASE_URL}/templates/${id}/`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new ApiValidationError(detail);
  }
  return res.json();
}

// ---------------------------------------------------------------------------
// MissionTemplate create
// ---------------------------------------------------------------------------

export async function createMissionTemplate(
  body: Partial<MissionTemplate>
): Promise<MissionTemplate> {
  const res = await apiFetch(`${BASE_URL}/templates/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new ApiValidationError(detail);
  }
  return res.json();
}

// ---------------------------------------------------------------------------
// MissionCategory read-only browse
// ---------------------------------------------------------------------------

/**
 * Loads up to 100 categories in one request (backend's max_page_size cap).
 * If the category set ever exceeds 100, switch to useInfiniteQuery or
 * surface a paginated picker UI.
 */
export async function listMissionCategories(): Promise<PaginatedResponse<MissionCategory>> {
  const res = await apiFetch(`${BASE_URL}/categories/?page_size=100`);
  if (!res.ok) throw new Error('Failed to load categories');
  return res.json();
}

// ---------------------------------------------------------------------------
// MissionNode (D2)
// ---------------------------------------------------------------------------

export async function listMissionNodes(
  filters: {
    template?: number;
    is_entry?: boolean;
    needs_rewrite?: boolean;
    page?: number;
    page_size?: number;
  } = {}
): Promise<PaginatedResponse<MissionNode>> {
  const res = await apiFetch(`${BASE_URL}/nodes/${buildQueryString(filters)}`);
  if (!res.ok) throw new Error('Failed to load nodes');
  return res.json();
}

export async function getMissionNode(id: number): Promise<MissionNode> {
  const res = await apiFetch(`${BASE_URL}/nodes/${id}/`);
  if (!res.ok) throw new Error(`Failed to load node ${id}`);
  return res.json();
}

export async function patchMissionNode(
  id: number,
  body: Partial<MissionNode>
): Promise<MissionNode> {
  const res = await apiFetch(`${BASE_URL}/nodes/${id}/`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error('Failed to update node');
  return res.json();
}

export async function getMissionOption(id: number): Promise<MissionOption> {
  const res = await apiFetch(`${BASE_URL}/options/${id}/`);
  if (!res.ok) throw new Error(`Failed to load option ${id}`);
  return res.json();
}

export async function patchMissionOption(
  id: number,
  body: Partial<MissionOption>
): Promise<MissionOption> {
  const res = await apiFetch(`${BASE_URL}/options/${id}/`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error('Failed to update option');
  return res.json();
}

// ---------------------------------------------------------------------------
// MissionOption / Route / Candidate / Reward (D2)
// ---------------------------------------------------------------------------

export async function listMissionOptions(
  filters: {
    node?: number;
    template?: number;
    needs_rewrite?: boolean;
  } = {}
): Promise<PaginatedResponse<MissionOption>> {
  const res = await apiFetch(`${BASE_URL}/options/${buildQueryString(filters)}`);
  if (!res.ok) throw new Error('Failed to load options');
  return res.json();
}

export async function listMissionRoutes(
  filters: {
    option?: number;
    template?: number;
    needs_rewrite?: boolean;
  } = {}
): Promise<PaginatedResponse<MissionOptionRoute>> {
  const res = await apiFetch(`${BASE_URL}/routes/${buildQueryString(filters)}`);
  if (!res.ok) throw new Error('Failed to load routes');
  return res.json();
}

export async function listRouteCandidates(
  filters: {
    route?: number;
  } = {}
): Promise<PaginatedResponse<MissionOptionRouteCandidate>> {
  const res = await apiFetch(`${BASE_URL}/route-candidates/${buildQueryString(filters)}`);
  if (!res.ok) throw new Error('Failed to load candidates');
  return res.json();
}

export async function listRouteRewards(
  filters: {
    route?: number;
    candidate?: number;
  } = {}
): Promise<PaginatedResponse<MissionOptionRouteReward>> {
  const res = await apiFetch(`${BASE_URL}/route-rewards/${buildQueryString(filters)}`);
  if (!res.ok) throw new Error('Failed to load rewards');
  return res.json();
}

// ---------------------------------------------------------------------------
// Givers (D3)
// ---------------------------------------------------------------------------

export async function listMissionGivers(
  filters: {
    org?: number;
    org_name?: string;
    giver_kind?: string;
    is_active?: boolean;
    name?: string;
  } = {}
): Promise<PaginatedResponse<MissionGiver>> {
  const res = await apiFetch(`${BASE_URL}/givers/${buildQueryString(filters)}`);
  if (!res.ok) throw new Error('Failed to load givers');
  return res.json();
}

export async function getMissionGiver(id: number): Promise<MissionGiver> {
  const res = await apiFetch(`${BASE_URL}/givers/${id}/`);
  if (!res.ok) throw new Error(`Failed to load giver ${id}`);
  return res.json();
}

export async function listGiverOfferings(
  filters: {
    giver?: number;
    template?: number;
  } = {}
): Promise<PaginatedResponse<MissionGiverOffering>> {
  const res = await apiFetch(`${BASE_URL}/giver-offerings/${buildQueryString(filters)}`);
  if (!res.ok) throw new Error('Failed to load offerings');
  return res.json();
}

export async function listGiverStandings(
  filters: {
    giver?: number;
    character?: number;
  } = {}
): Promise<PaginatedResponse<MissionGiverStanding>> {
  const res = await apiFetch(`${BASE_URL}/giver-standings/${buildQueryString(filters)}`);
  if (!res.ok) throw new Error('Failed to load standings');
  return res.json();
}

export async function createMissionGiver(body: Partial<MissionGiver>): Promise<MissionGiver> {
  const res = await apiFetch(`${BASE_URL}/givers/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(
      typeof detail === 'object' && detail !== null
        ? JSON.stringify(detail)
        : 'Failed to create giver'
    );
  }
  return res.json();
}

export async function patchMissionGiver(
  id: number,
  body: Partial<MissionGiver>
): Promise<MissionGiver> {
  const res = await apiFetch(`${BASE_URL}/givers/${id}/`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(
      typeof detail === 'object' && detail !== null
        ? JSON.stringify(detail)
        : 'Failed to update giver'
    );
  }
  return res.json();
}

export async function deleteMissionGiver(id: number): Promise<void> {
  const res = await apiFetch(`${BASE_URL}/givers/${id}/`, { method: 'DELETE' });
  if (!res.ok) throw new Error('Failed to delete giver');
}

export async function createGiverOffering(
  body: Partial<MissionGiverOffering>
): Promise<MissionGiverOffering> {
  const res = await apiFetch(`${BASE_URL}/giver-offerings/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(
      typeof detail === 'object' && detail !== null
        ? JSON.stringify(detail)
        : 'Failed to add offering'
    );
  }
  return res.json();
}

export async function patchGiverOffering(
  id: number,
  body: Partial<MissionGiverOffering>
): Promise<MissionGiverOffering> {
  const res = await apiFetch(`${BASE_URL}/giver-offerings/${id}/`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(
      typeof detail === 'object' && detail !== null
        ? JSON.stringify(detail)
        : 'Failed to update offering'
    );
  }
  return res.json();
}

export async function deleteGiverOffering(id: number): Promise<void> {
  const res = await apiFetch(`${BASE_URL}/giver-offerings/${id}/`, { method: 'DELETE' });
  if (!res.ok) throw new Error('Failed to remove offering');
}

// ---------------------------------------------------------------------------
// Copy actions (D4.2)
// ---------------------------------------------------------------------------

export async function copyTemplate(
  id: number,
  body: { new_name?: string }
): Promise<MissionTemplate> {
  const res = await apiFetch(`${BASE_URL}/templates/${id}/copy/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    // Mirror createMissionTemplate: parse the body and throw ApiValidationError
    // so consumers (StaffActionsCard CopyRow) can surface specific field messages
    // (e.g. {"new_name": ["May not be blank."]}), not just "Failed to copy template".
    const detail = await res.json().catch(() => ({}));
    throw new ApiValidationError(detail);
  }
  return res.json();
}

export async function copyNode(id: number, body: { new_key: string }): Promise<MissionNode> {
  const res = await apiFetch(`${BASE_URL}/nodes/${id}/copy/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error('Failed to copy node');
  return res.json();
}

export async function copySubtree(
  id: number,
  body: { new_key_prefix: string }
): Promise<MissionNode> {
  const res = await apiFetch(`${BASE_URL}/nodes/${id}/copy-subtree/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error('Failed to copy subtree');
  return res.json();
}

// ---------------------------------------------------------------------------
// Staff-power (D4.3)
// ---------------------------------------------------------------------------

export async function assignMission(
  id: number,
  body: { character: number }
): Promise<MissionInstance> {
  const res = await apiFetch(`${BASE_URL}/templates/${id}/assign/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error('Failed to assign mission');
  return res.json();
}

export async function deleteMissionInstance(id: number): Promise<void> {
  const res = await apiFetch(`${BASE_URL}/instances/${id}/`, { method: 'DELETE' });
  if (!res.ok) throw new Error('Failed to remove instance');
}

// ---------------------------------------------------------------------------
// Predicate-leaf catalog (D5)
// ---------------------------------------------------------------------------

/** Type tags emitted by the D5 catalog so the FE can coerce <Input> strings. */
export type PredicateParamType = 'str' | 'int' | 'bool' | 'float';

export interface PredicateLeafParam {
  name: string;
  type: PredicateParamType;
}

export interface PredicateLeaf {
  name: string;
  params: PredicateLeafParam[];
}

export async function listPredicateLeaves(): Promise<PredicateLeaf[]> {
  const res = await apiFetch(`${BASE_URL}/predicate-leaves/`);
  if (!res.ok) throw new Error('Failed to load predicate leaves');
  return res.json();
}

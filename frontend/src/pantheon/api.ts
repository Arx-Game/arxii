/**
 * Deity Editor API client (#3780): `/api/worship/admin/beings/` and its dashboard actions,
 * all staff only. Sending a vision from a being's page reuses the worship vision POST.
 */

import { apiFetch, withQuery } from '@/evennia_replacements/api';
import { throwApiError } from '@/lib/errors';
import type { PaginatedResponse } from '@/shared/types';
import type { VisionCreate } from '@/worship/types';
import type {
  CodexRow,
  EditorOptions,
  Overview,
  RelicRow,
  RosterCharacterRef,
  SiteRow,
  StaffBeingList,
  StaffBeingPage,
  StaffBeingPageRequest,
  StaffPrayer,
  StaffVision,
  Visibility,
  WorshipTab,
} from './types';

const BASE = '/api/worship/admin/beings/';

async function getJson<T>(url: string, fallback: string): Promise<T> {
  const res = await apiFetch(url);
  if (!res.ok) await throwApiError(res, fallback);
  return (await res.json()) as T;
}

export interface BeingListParams {
  search?: string;
  visibility?: Visibility;
  page?: number;
}

export function fetchBeings(
  params: BeingListParams = {}
): Promise<PaginatedResponse<StaffBeingList>> {
  const query = new URLSearchParams();
  if (params.search) query.set('search', params.search);
  if (params.visibility) query.set('visibility', params.visibility);
  if (params.page) query.set('page', String(params.page));
  query.set('page_size', '100');
  return getJson(withQuery(BASE, query), 'Failed to load the pantheon.');
}

export function fetchBeingPage(id: number): Promise<StaffBeingPage> {
  return getJson(`${BASE}${id}/`, 'Failed to load the god.');
}

export function fetchEditorOptions(): Promise<EditorOptions> {
  return getJson(`${BASE}options/`, "Failed to load the editor's choices.");
}

export async function saveBeingPage(
  id: number | null,
  page: StaffBeingPageRequest
): Promise<StaffBeingPage> {
  const res = await apiFetch(id === null ? BASE : `${BASE}${id}/`, {
    method: id === null ? 'POST' : 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(page),
  });
  if (!res.ok) await throwApiError(res, 'The god could not be saved.');
  return (await res.json()) as StaffBeingPage;
}

export function fetchOverview(id: number): Promise<Overview> {
  return getJson(`${BASE}${id}/overview/`, 'Failed to load the overview.');
}

export function fetchWorshipTab(id: number): Promise<WorshipTab> {
  return getJson(`${BASE}${id}/worship/`, 'Failed to load worship.');
}

export function fetchSites(id: number): Promise<SiteRow[]> {
  return getJson(`${BASE}${id}/sites/`, 'Failed to load the sites.');
}

export function fetchBeingPrayers(id: number): Promise<PaginatedResponse<StaffPrayer>> {
  return getJson(`${BASE}${id}/prayers/?page_size=50`, 'Failed to load the prayers.');
}

export function fetchBeingVisions(id: number): Promise<PaginatedResponse<StaffVision>> {
  return getJson(`${BASE}${id}/visions/?page_size=50`, 'Failed to load the visions.');
}

export function fetchRelics(id: number): Promise<RelicRow[]> {
  return getJson(`${BASE}${id}/relics/`, 'Failed to load the relics.');
}

export function fetchCodexRows(id: number): Promise<CodexRow[]> {
  return getJson(`${BASE}${id}/codex/`, 'Failed to load the codex entries.');
}

/** Characters by name, for the Send-vision recipient picker. */
export async function searchRosterCharacters(name: string): Promise<RosterCharacterRef[]> {
  const query = new URLSearchParams({ name, page_size: '20' });
  const data = await getJson<PaginatedResponse<RosterCharacterRef> | RosterCharacterRef[]>(
    withQuery('/api/roster/entries/', query),
    'Failed to search characters.'
  );
  return Array.isArray(data) ? data : data.results;
}

export async function sendVisionFromBeing(payload: VisionCreate): Promise<void> {
  const res = await apiFetch('/api/worship/visions/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) await throwApiError(res, 'The vision could not be sent.');
}

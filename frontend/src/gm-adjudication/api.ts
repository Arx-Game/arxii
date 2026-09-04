/**
 * REST reads for the GM adjudication toolkit's catalog pickers (#3070).
 *
 * Three of the four catalogs already existed for other surfaces
 * (`ConditionTemplateViewSet`, `SituationTemplateViewSet`,
 * `ChallengeTemplateViewSet`) — reused as-is. Only `CheckType` needed a new
 * endpoint (`world/checks/views.py::CheckTypeViewSet`,
 * `GET /api/checks/check-types/`).
 */

import { apiFetch } from '@/evennia_replacements/api';
import type {
  ChallengeTemplateCatalogEntry,
  CheckTypeCatalogEntry,
  ConditionTemplateCatalogEntry,
  DiscoveryResult,
  GMSummonOfferEntry,
  ItemTemplateCatalogEntry,
  SituationTemplateCatalogEntry,
} from './types';

async function throwOnBadResponse(res: Response, fallbackMessage: string): Promise<void> {
  if (res.ok) return;
  throw new Error(fallbackMessage);
}

export async function getCheckTypeCatalog(search?: string): Promise<CheckTypeCatalogEntry[]> {
  const params = new URLSearchParams({ page_size: '50' });
  if (search) params.set('search', search);
  const res = await apiFetch(`/api/checks/check-types/?${params.toString()}`);
  await throwOnBadResponse(res, 'Failed to load check catalog');
  const data = (await res.json()) as { results?: CheckTypeCatalogEntry[] };
  return data.results ?? [];
}

export async function getConditionTemplateCatalog(): Promise<ConditionTemplateCatalogEntry[]> {
  const res = await apiFetch('/api/conditions/templates/');
  await throwOnBadResponse(res, 'Failed to load condition catalog');
  // pagination_class=None on this endpoint — a bare array, not a paginated wrapper.
  return (await res.json()) as ConditionTemplateCatalogEntry[];
}

export async function getSituationTemplateCatalog(): Promise<SituationTemplateCatalogEntry[]> {
  const res = await apiFetch('/api/mechanics/situation-templates/?page_size=100');
  await throwOnBadResponse(res, 'Failed to load situation catalog');
  const data = (await res.json()) as { results?: SituationTemplateCatalogEntry[] };
  return data.results ?? [];
}

export async function getChallengeTemplateCatalog(): Promise<ChallengeTemplateCatalogEntry[]> {
  const res = await apiFetch('/api/mechanics/challenge-templates/?page_size=100');
  await throwOnBadResponse(res, 'Failed to load challenge catalog');
  const data = (await res.json()) as { results?: ChallengeTemplateCatalogEntry[] };
  return data.results ?? [];
}

/**
 * Item template catalog for the Grant Item / Stage Prop pickers (#3431).
 * Reuses `ItemTemplateViewSet` (`items/views.py:265`) — `name` is its
 * `django_filters.CharFilter(lookup_expr="icontains")`, not a generic
 * DRF `search` param (Decision 3, no new endpoint).
 */
export async function getItemTemplateCatalog(search?: string): Promise<ItemTemplateCatalogEntry[]> {
  const params = new URLSearchParams({ page_size: '50' });
  if (search) params.set('name', search);
  const res = await apiFetch(`/api/items/templates/?${params.toString()}`);
  await throwOnBadResponse(res, 'Failed to load item template catalog');
  const data = (await res.json()) as { results?: ItemTemplateCatalogEntry[] };
  return data.results ?? [];
}

/**
 * The requesting player's pending GM summon offer(s) (#3071).
 * GET /api/gm/summon-offers/ — bare array, `pagination_class = None`.
 */
export async function fetchSummonOfferInbox(): Promise<GMSummonOfferEntry[]> {
  const res = await apiFetch('/api/gm/summon-offers/');
  await throwOnBadResponse(res, 'Failed to load pending summons');
  return (await res.json()) as GMSummonOfferEntry[];
}

/**
 * GET /api/gm/discovery/: kind-first catalog browse (#3564). Empty q =
 * kinds only. Same search as telnet `setsituation find`.
 */
export async function getDiscovery(q: string, risk: string | null): Promise<DiscoveryResult> {
  const params = new URLSearchParams();
  if (q) params.set('q', q);
  if (risk) params.set('risk', risk);
  const qs = params.toString();
  const query = qs ? `?${qs}` : '';
  const res = await apiFetch(`/api/gm/discovery/${query}`);
  await throwOnBadResponse(res, 'Failed to load discovery catalog');
  return (await res.json()) as DiscoveryResult;
}

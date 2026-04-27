/**
 * Narrative API functions
 *
 * Read endpoints for the recipient's narrative messages and the
 * acknowledge action. Wave 8 adds Gemit read and broadcast endpoints.
 *
 * Uses apiFetch from @/evennia_replacements/api and BASE_URL = '/api/narrative'.
 */

import { apiFetch } from '@/evennia_replacements/api';
import type {
  BroadcastGemitBody,
  Gemit,
  GemitListParams,
  MyMessagesQueryParams,
  NarrativeMessageDelivery,
  PaginatedDeliveries,
  PaginatedGemits,
} from './types';

const BASE_URL = '/api/narrative';

export async function getMyMessages(params?: MyMessagesQueryParams): Promise<PaginatedDeliveries> {
  const search = new URLSearchParams();
  if (params?.category) search.set('category', params.category);
  if (params?.acknowledged !== undefined) {
    search.set('acknowledged', String(params.acknowledged));
  }
  if (params?.page) search.set('page', String(params.page));
  const qs = search.toString();
  const res = await apiFetch(`${BASE_URL}/my-messages/${qs ? `?${qs}` : ''}`);
  if (!res.ok) {
    throw new Error('Failed to load narrative messages');
  }
  return res.json() as Promise<PaginatedDeliveries>;
}

export async function acknowledgeDelivery(deliveryId: number): Promise<NarrativeMessageDelivery> {
  const res = await apiFetch(`${BASE_URL}/deliveries/${deliveryId}/acknowledge/`, {
    method: 'POST',
  });
  if (!res.ok) {
    throw new Error('Failed to acknowledge message');
  }
  return res.json() as Promise<NarrativeMessageDelivery>;
}

// ---------------------------------------------------------------------------
// Gemit endpoints (Wave 8)
// ---------------------------------------------------------------------------

/**
 * GET /api/narrative/gemits/
 * Paginated public read of broadcast gemits.
 * Optional filters: related_era, related_story, page.
 */
export async function getGemits(params?: GemitListParams): Promise<PaginatedGemits> {
  const search = new URLSearchParams();
  if (params?.related_era !== undefined) search.set('related_era', String(params.related_era));
  if (params?.related_story !== undefined)
    search.set('related_story', String(params.related_story));
  if (params?.page !== undefined) search.set('page', String(params.page));
  const qs = search.toString();
  const res = await apiFetch(`${BASE_URL}/gemits/${qs ? `?${qs}` : ''}`);
  if (!res.ok) {
    throw new Error('Failed to load gemits');
  }
  return res.json() as Promise<PaginatedGemits>;
}

/**
 * POST /api/narrative/gemits/
 * Staff-only broadcast. Returns 201 with the created Gemit.
 */
export async function broadcastGemit(data: BroadcastGemitBody): Promise<Gemit> {
  const res = await apiFetch(`${BASE_URL}/gemits/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const err = new Error('Failed to broadcast gemit') as Error & { status?: number };
    err.status = res.status;
    throw err;
  }
  return res.json() as Promise<Gemit>;
}

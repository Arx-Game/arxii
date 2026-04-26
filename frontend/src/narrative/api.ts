/**
 * Narrative API functions
 *
 * Read endpoints for the recipient's narrative messages and the
 * acknowledge action. Write/composer endpoints are deferred until
 * the backend sender endpoint and the messages-section UI ship
 * together (Phase 4+).
 *
 * Uses apiFetch from @/evennia_replacements/api and BASE_URL = '/api/narrative'.
 */

import { apiFetch } from '@/evennia_replacements/api';
import type { MyMessagesQueryParams, NarrativeMessageDelivery, PaginatedDeliveries } from './types';

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

/**
 * Player-facing NPC interaction client (#930): start / resolve / end against
 * the InteractionViewSet state machine. One interaction in flight per session
 * (the backend enforces it with a 409).
 */

import { apiFetch } from '@/evennia_replacements/api';
import type { components } from '@/generated/api';

export type InteractionState = components['schemas']['InteractionState'];
export type InteractionOffer = components['schemas']['InteractionOffer'];

const BASE = '/api/npc-services/interactions';

async function post<T>(url: string, body: Record<string, unknown>): Promise<T> {
  const res = await apiFetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = 'The interaction failed.';
    try {
      const data = (await res.json()) as { detail?: string };
      if (typeof data.detail === 'string' && data.detail.trim()) {
        detail = data.detail;
      }
    } catch {
      // body wasn't JSON; keep the generic message
    }
    throw new Error(detail);
  }
  return (await res.json()) as T;
}

export function startInteraction(roleId: number): Promise<InteractionState> {
  return post(`${BASE}/start/`, { role_id: roleId });
}

export function resolveOffer(offerId: number): Promise<InteractionState> {
  return post(`${BASE}/resolve/`, { offer_id: offerId });
}

export function endInteraction(): Promise<InteractionState> {
  return post(`${BASE}/end/`, {});
}

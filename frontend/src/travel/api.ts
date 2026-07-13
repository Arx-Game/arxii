/**
 * Travel API client functions (#2352).
 *
 * Plain async functions — not hooks. React Query hooks live in queries.ts.
 * Mutations dispatch through the standard action seam via postDispatchAction.
 */

import { apiFetch } from '@/evennia_replacements/api';
import { postDispatchAction } from '@/combat/api';
import type { TravelHub, TravelMethod, Voyage, VoyageInvite } from './types';

export async function fetchHubs(): Promise<TravelHub[]> {
  const res = await apiFetch('/api/travel/hubs/');
  if (!res.ok) throw new Error('Failed to fetch travel hubs');
  return res.json();
}

export async function fetchMethods(): Promise<TravelMethod[]> {
  const res = await apiFetch('/api/travel/methods/');
  if (!res.ok) throw new Error('Failed to fetch travel methods');
  return res.json();
}

export async function fetchVoyages(): Promise<Voyage[]> {
  const res = await apiFetch('/api/travel/voyages/');
  if (!res.ok) throw new Error('Failed to fetch voyages');
  return res.json();
}

export async function fetchPendingInvites(): Promise<VoyageInvite[]> {
  const res = await apiFetch('/api/travel/invites/');
  if (!res.ok) throw new Error('Failed to fetch voyage invites');
  return res.json();
}

export function dispatchVoyageAction(
  characterId: number,
  registryKey: string,
  kwargs: Record<string, unknown> = {}
) {
  return postDispatchAction(characterId, {
    ref: { backend: 'registry', registry_key: registryKey },
    kwargs,
  });
}

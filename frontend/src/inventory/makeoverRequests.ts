/**
 * The makeover ask (#4187): a stylist's offer to restyle your character, waiting on
 * your answer. The server lists the asks addressed to any character you play (after
 * dropping any whose stylist has left the room); `respond` grants or declines, with the
 * optional one-motion shortcut that whitelists ("always") or blacklists ("never") them.
 */
import { apiFetch } from '@/evennia_replacements/api';
import { readErrorDetail } from '@/lib/errors';
import type { components } from '@/generated/api';

export type MakeoverConsentRequest = components['schemas']['MakeoverConsentRequest'];
export type MakeoverDecision = 'grant' | 'decline';
export type MakeoverRemember = 'always' | 'never';

export const MAKEOVER_REQUESTS_QUERY_KEY = ['makeover-requests'] as const;

export async function fetchPendingMakeoverRequests(): Promise<MakeoverConsentRequest[]> {
  const res = await apiFetch('/api/items/makeover-requests/');
  if (!res.ok) await readErrorDetail(res, 'Failed to load makeover offers');
  return res.json() as Promise<MakeoverConsentRequest[]>;
}

export async function respondToMakeoverRequest(
  requestId: number,
  decision: MakeoverDecision,
  remember: MakeoverRemember | null
): Promise<{ status: string }> {
  const res = await apiFetch(`/api/items/makeover-requests/${requestId}/respond/`, {
    method: 'POST',
    body: JSON.stringify({ decision, remember }),
  });
  if (!res.ok) await readErrorDetail(res, 'Failed to answer the makeover offer');
  return res.json() as Promise<{ status: string }>;
}

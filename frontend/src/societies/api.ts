import { apiFetch } from '@/evennia_replacements/api';
import type { OfferResponse, OrganizationMembershipOffer, PaginatedOffers } from './types';

/**
 * Pending organization membership offers visible to the caller
 * (`OrganizationMembershipOfferViewSet.get_queryset` already scopes to
 * offers the account owns, received, or can see via org membership — see
 * #3412 T1). Callers filter further client-side (e.g. to `to_persona`
 * mine) — mirrors `events/queries.ts`'s invitation-list pattern.
 */
export async function fetchPendingMembershipOffers(): Promise<PaginatedOffers> {
  const res = await apiFetch('/api/societies/offers/?status=pending');
  if (!res.ok) throw new Error('Failed to load organization offers');
  return res.json();
}

/**
 * Accept/decline a membership offer (#3412 T1 — `OrganizationMembershipOfferViewSet.respond`).
 * Returns the updated offer (not a `{success, message}` envelope — see T1's report).
 */
export async function respondToMembershipOffer(
  offerId: number,
  response: OfferResponse
): Promise<OrganizationMembershipOffer> {
  const res = await apiFetch(`/api/societies/offers/${offerId}/respond/`, {
    method: 'POST',
    body: JSON.stringify({ response }),
  });
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data.detail || 'Failed to send your response');
  }
  return data;
}

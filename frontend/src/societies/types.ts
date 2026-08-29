/**
 * Societies (organizations) types — hand-defined for the pieces #3412's Hall
 * needs. `OrganizationMembershipOffer` is already in the generated schema
 * (introspected from `OrganizationMembershipOfferSerializer`); the `respond`
 * action T1 added (`POST /api/societies/offers/{id}/respond/`) is NOT yet in
 * the generated schema (regen is Task 4's job) so its request/response
 * shapes are hand-declared here, mirroring `events/types.ts`'s
 * `InvitationResponse` pattern.
 */

import type { components } from '@/generated/api';

export type OrganizationMembershipOffer = components['schemas']['OrganizationMembershipOffer'];

export type OfferResponse = 'accept' | 'decline';

export interface PaginatedOffers {
  count: number;
  next: string | null;
  previous: string | null;
  results: OrganizationMembershipOffer[];
}

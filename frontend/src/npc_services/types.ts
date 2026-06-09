/**
 * NPC-services staff editor types (#728 — Mission Studio).
 *
 * Aliases over the generated OpenAPI schema so the editor pages stay in sync
 * with the backend `NPCRole` / `NPCServiceOffer` / `MissionOfferDetails` surface.
 */
import type { components } from '@/generated/api';

export type NPCRole = components['schemas']['NPCRole'];
export type NPCRoleRequest = components['schemas']['NPCRoleRequest'];
export type NPCServiceOffer = components['schemas']['NPCServiceOffer'];
export type NPCServiceOfferRequest = components['schemas']['NPCServiceOfferRequest'];
export type MissionOfferDetails = components['schemas']['MissionOfferDetails'];
export type MissionOfferDetailsRequest = components['schemas']['MissionOfferDetailsRequest'];

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface NPCRoleFilters {
  name?: string;
  faction_affiliation?: number;
  page?: number;
  page_size?: number;
}

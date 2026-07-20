/** Hand-rolled — the accept/decline actions return a plain dict, not a
 * generated serializer response (mirrors the MotifStyleBindingsResponse
 * precedent in frontend/src/magic/types.ts). */

export interface SeanceOffer {
  id: number;
  honoree_name: string;
  ceremony_location_name: string;
  ceremony_id: number;
  status: 'pending' | 'accepted' | 'declined';
  created_at: string;
}

export interface SeanceOfferRespondResult {
  detail: string;
  offer_id?: number;
  status?: string;
}

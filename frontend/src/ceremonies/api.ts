import { apiFetch } from '@/evennia_replacements/api';
import type { SeanceOffer, SeanceOfferRespondResult } from './types';

export async function getSeanceOffers(): Promise<SeanceOffer[]> {
  const res = await apiFetch('/api/ceremonies/seance-offers/');
  if (!res.ok) {
    throw new Error('Failed to load seance offers');
  }
  return res.json();
}

async function respondToSeanceOffer(
  offerId: number,
  verb: 'accept' | 'decline'
): Promise<SeanceOfferRespondResult> {
  const res = await apiFetch(`/api/ceremonies/seance-offers/${offerId}/${verb}/`, {
    method: 'POST',
  });
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data.detail ?? 'Failed to respond to the seance offer');
  }
  return data;
}

export function acceptSeanceOffer(offerId: number): Promise<SeanceOfferRespondResult> {
  return respondToSeanceOffer(offerId, 'accept');
}

export function declineSeanceOffer(offerId: number): Promise<SeanceOfferRespondResult> {
  return respondToSeanceOffer(offerId, 'decline');
}

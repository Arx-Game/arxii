import { apiFetch } from '@/evennia_replacements/api';
import type {
  ConversionOffer,
  ConversionOfferRespondResult,
  SeanceOffer,
  SeanceOfferRespondResult,
} from './types';

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

export async function getConversionOffers(): Promise<ConversionOffer[]> {
  const res = await apiFetch('/api/ceremonies/conversion-offers/');
  if (!res.ok) {
    throw new Error('Failed to load conversion offers');
  }
  return res.json();
}

async function respondToConversionOffer(
  offerId: number,
  verb: 'accept' | 'decline',
  sincere?: boolean
): Promise<ConversionOfferRespondResult> {
  const res = await apiFetch(`/api/ceremonies/conversion-offers/${offerId}/${verb}/`, {
    method: 'POST',
    body: JSON.stringify(verb === 'accept' ? { sincere: sincere ?? true } : {}),
  });
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data.detail ?? 'Failed to respond to the conversion offer');
  }
  return data;
}

export function acceptConversionOffer(
  offerId: number,
  sincere: boolean
): Promise<ConversionOfferRespondResult> {
  return respondToConversionOffer(offerId, 'accept', sincere);
}

export function declineConversionOffer(offerId: number): Promise<ConversionOfferRespondResult> {
  return respondToConversionOffer(offerId, 'decline');
}

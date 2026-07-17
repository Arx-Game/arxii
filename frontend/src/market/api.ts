/**
 * Market center API (#2066): read the squares/listings/directory; every
 * mutation dispatches a REGISTRY action — the same seam telnet uses.
 */

import { apiFetch } from '@/evennia_replacements/api';
import { throwApiError } from '@/lib/errors';

export interface StockListing {
  id: number;
  template: number;
  template_name: string;
  price: number;
}

export interface WareListing {
  id: number;
  item_instance: number;
  item_name: string;
  seller_name: string;
  price: number;
  open_style_slot: boolean;
  open_facet_slot: boolean;
  listed_at: string;
}

export interface MarketStall {
  id: number;
  name: string;
  owner_name: string;
  stock_listings: StockListing[];
  ware_listings: WareListing[];
}

export interface MarketSquare {
  id: number;
  name: string;
  realm: number | null;
  stalls: MarketStall[];
}

export interface ServiceOffer {
  id: number;
  crafter_name: string;
  recipe_kind: string;
  fee: number;
  shop_room_id: number;
}

interface Paginated<T> {
  results: T[];
}

export async function getMarketSquares(): Promise<MarketSquare[]> {
  const res = await apiFetch('/api/items/market-squares/');
  if (!res.ok) {
    throw new Error('Failed to load market squares');
  }
  const data = (await res.json()) as Paginated<MarketSquare> | MarketSquare[];
  return Array.isArray(data) ? data : data.results;
}

export async function getServiceOffers(): Promise<ServiceOffer[]> {
  const res = await apiFetch('/api/items/service-offers/');
  if (!res.ok) {
    throw new Error('Failed to load the shop directory');
  }
  const data = (await res.json()) as Paginated<ServiceOffer> | ServiceOffer[];
  return Array.isArray(data) ? data : data.results;
}

export type MarketActionKey = 'market_buy_stock' | 'market_buy_ware' | 'market_finish_ware';

export async function dispatchMarketAction(
  characterId: number,
  registryKey: MarketActionKey,
  kwargs: Record<string, unknown>
): Promise<string> {
  const res = await apiFetch(`/api/actions/characters/${characterId}/dispatch/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ref: { backend: 'registry', registry_key: registryKey }, kwargs }),
  });
  if (!res.ok) await throwApiError(res, 'The action failed.');
  const data = (await res.json()) as { message?: string };
  return data.message ?? 'Done.';
}

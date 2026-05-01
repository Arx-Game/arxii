/**
 * Inventory / Outfits API functions.
 *
 * Mirrors the codex/events feature pattern: thin wrappers over apiFetch that
 * unwrap DRF responses and surface useful error messages.
 *
 * Equip/unequip and apply/undress flow through the websocket action
 * dispatcher (see Task 13) — REST stays read-only for inventory state.
 */

import { apiFetch } from '@/evennia_replacements/api';
import type {
  CreateOutfitPayload,
  CreateOutfitSlotPayload,
  EquippedItem,
  ItemInstance,
  Outfit,
  OutfitSlot,
  PaginatedResponse,
  UpdateOutfitPayload,
} from './types';

const BASE_URL = '/api/items';

async function readError(res: Response, fallback: string): Promise<string> {
  try {
    const err = await res.json();
    return err.detail || err.non_field_errors?.[0] || fallback;
  } catch {
    return fallback;
  }
}

// ---------------------------------------------------------------------------
// Outfits
// ---------------------------------------------------------------------------

export async function listOutfits(characterSheetId: number): Promise<Outfit[]> {
  const res = await apiFetch(`${BASE_URL}/outfits/?character_sheet=${characterSheetId}`);
  if (!res.ok) {
    throw new Error(await readError(res, 'Failed to load outfits'));
  }
  const data = (await res.json()) as PaginatedResponse<Outfit>;
  return data.results;
}

export async function getOutfit(id: number): Promise<Outfit> {
  const res = await apiFetch(`${BASE_URL}/outfits/${id}/`);
  if (!res.ok) {
    throw new Error(await readError(res, 'Failed to load outfit'));
  }
  return res.json();
}

export async function createOutfit(payload: CreateOutfitPayload): Promise<Outfit> {
  const res = await apiFetch(`${BASE_URL}/outfits/`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    throw new Error(await readError(res, 'Failed to create outfit'));
  }
  return res.json();
}

export async function updateOutfit(id: number, payload: UpdateOutfitPayload): Promise<Outfit> {
  const res = await apiFetch(`${BASE_URL}/outfits/${id}/`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    throw new Error(await readError(res, 'Failed to update outfit'));
  }
  return res.json();
}

export async function deleteOutfit(id: number): Promise<void> {
  const res = await apiFetch(`${BASE_URL}/outfits/${id}/`, { method: 'DELETE' });
  if (res.status !== 204) {
    throw new Error(await readError(res, 'Failed to delete outfit'));
  }
}

// ---------------------------------------------------------------------------
// Outfit slots
// ---------------------------------------------------------------------------

export async function listOutfitSlots(outfitId: number): Promise<OutfitSlot[]> {
  const res = await apiFetch(`${BASE_URL}/outfit-slots/?outfit=${outfitId}`);
  if (!res.ok) {
    throw new Error(await readError(res, 'Failed to load outfit slots'));
  }
  const data = (await res.json()) as PaginatedResponse<OutfitSlot>;
  return data.results;
}

export async function createOutfitSlot(payload: CreateOutfitSlotPayload): Promise<OutfitSlot> {
  const res = await apiFetch(`${BASE_URL}/outfit-slots/`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    throw new Error(await readError(res, 'Failed to add outfit slot'));
  }
  return res.json();
}

export async function deleteOutfitSlot(id: number): Promise<void> {
  const res = await apiFetch(`${BASE_URL}/outfit-slots/${id}/`, { method: 'DELETE' });
  if (res.status !== 204) {
    throw new Error(await readError(res, 'Failed to remove outfit slot'));
  }
}

// ---------------------------------------------------------------------------
// Inventory + equipped (read-only)
// ---------------------------------------------------------------------------

export async function listInventory(characterId: number): Promise<ItemInstance[]> {
  const res = await apiFetch(`${BASE_URL}/inventory/?character=${characterId}`);
  if (!res.ok) {
    throw new Error(await readError(res, 'Failed to load inventory'));
  }
  const data = (await res.json()) as PaginatedResponse<ItemInstance>;
  return data.results;
}

export async function listEquipped(characterId: number): Promise<EquippedItem[]> {
  const res = await apiFetch(`${BASE_URL}/equipped-items/?character=${characterId}`);
  if (!res.ok) {
    throw new Error(await readError(res, 'Failed to load equipped items'));
  }
  const data = (await res.json()) as PaginatedResponse<EquippedItem>;
  return data.results;
}

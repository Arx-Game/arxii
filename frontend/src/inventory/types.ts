/**
 * Inventory / Outfits feature types.
 *
 * Re-exports the OpenAPI-generated component schemas under shorter aliases
 * plus a couple of local types used by the wardrobe UI.
 */

import type { components } from '@/generated/api';

// ---------------------------------------------------------------------------
// Generated component aliases
// ---------------------------------------------------------------------------

export type Outfit = components['schemas']['OutfitRead'];
export type OutfitWriteRequest = components['schemas']['OutfitWriteRequest'];
export type PatchedOutfitWriteRequest = components['schemas']['PatchedOutfitWriteRequest'];

export type OutfitSlot = components['schemas']['OutfitSlotRead'];
export type OutfitSlotWriteRequest = components['schemas']['OutfitSlotWriteRequest'];

export type ItemInstance = components['schemas']['ItemInstanceRead'];
export type EquippedItem = components['schemas']['EquippedItemRead'];

export type BodyRegion = components['schemas']['BodyRegionEnum'];
export type EquipmentLayer = components['schemas']['EquipmentLayerEnum'];

// ---------------------------------------------------------------------------
// Paginated list responses (DRF)
// ---------------------------------------------------------------------------

export interface PaginatedResponse<T> {
  count: number;
  page_size?: number;
  num_pages?: number;
  current_page?: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

// ---------------------------------------------------------------------------
// Mutation payload shapes — keep separate from generated *WriteRequest types
// so callers don't need to import schema-internal names.
// ---------------------------------------------------------------------------

export interface CreateOutfitPayload {
  character_sheet: number;
  wardrobe: number;
  name: string;
  description?: string;
}

export interface UpdateOutfitPayload {
  name?: string;
  description?: string;
}

export interface CreateOutfitSlotPayload {
  outfit: number;
  item_instance: number;
  body_region: BodyRegion;
  equipment_layer: EquipmentLayer;
}

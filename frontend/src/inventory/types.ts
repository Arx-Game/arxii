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
// POST uses the full write serializer (snapshots current loadout). PUT/PATCH
// use the rename serializer (only name + description are mutable;
// character_sheet and wardrobe are write-once). See world.items.serializers
// for the distinction.
export type OutfitWriteRequest = components['schemas']['OutfitWriteRequest'];
export type OutfitRenameRequest = components['schemas']['OutfitRenameRequest'];
export type PatchedOutfitRenameRequest = components['schemas']['PatchedOutfitRenameRequest'];

export type OutfitSlot = components['schemas']['OutfitSlotRead'];
export type OutfitSlotWriteRequest = components['schemas']['OutfitSlotWriteRequest'];

export type ItemInstance = components['schemas']['ItemInstanceRead'];
export type EquippedItem = components['schemas']['EquippedItemRead'];
export type UseItemResult = components['schemas']['UseItemResult'];

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

// Lab station (#1234) install/upgrade/repair bodies. The generated schema
// doesn't type these request bodies — LabStationViewSet's install/upgrade/
// repair are custom @action methods validated by plain serializers.Serializer
// subclasses (world/items/serializers_station.py), which drf-spectacular
// doesn't infer a requestBody schema for. Hand-typed here, same as
// CreateOutfitPayload above.

export interface InstallLabStationPayload {
  room_profile_id: number;
  target_level: number;
}

export interface RepairLabStationPayload {
  restore_points: number;
}

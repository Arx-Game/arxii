/**
 * Inventory + equipped-items react-query hooks.
 *
 * Cache key shape:
 *   ["inventory", characterId]   — items currently held by the character
 *   ["equipped", characterId]    — items currently worn / wielded
 *
 * Both queries are read-only on the REST side. Mutations land via the
 * websocket action dispatcher (apply_outfit / undress / equip / unequip),
 * and the WS subscription handler (Task 13) is responsible for invalidating
 * these keys when state changes.
 */

import { useQuery } from '@tanstack/react-query';
import { listEquipped, listInventory } from '../api';

export const inventoryKeys = {
  all: ['inventory'] as const,
  inventory: (characterId: number) => ['inventory', characterId] as const,
  equipped: (characterId: number) => ['equipped', characterId] as const,
};

export function useInventory(characterId: number | undefined) {
  return useQuery({
    queryKey: inventoryKeys.inventory(characterId ?? -1),
    queryFn: () => listInventory(characterId as number),
    enabled: characterId != null,
    throwOnError: true,
  });
}

export function useEquippedItems(characterId: number | undefined) {
  return useQuery({
    queryKey: inventoryKeys.equipped(characterId ?? -1),
    queryFn: () => listEquipped(characterId as number),
    enabled: characterId != null,
    throwOnError: true,
  });
}

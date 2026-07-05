/**
 * InventorySidebarPanel — compact carried-items list on the game rail's
 * Inventory tab (#1446).
 *
 * Read-only: "the sheet describes; the scene does" — equip/use actions
 * belong to scene objects and the Wardrobe page, not this panel. It only
 * lists what's carried, marks what's currently worn, and links out to
 * /wardrobe for full management.
 */

import { useCallback, useMemo } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { Badge } from '@/components/ui/badge';
import { useActionResult } from '@/hooks/actionResultBus';
import type { ActionResultPayload } from '@/hooks/types';
import { ItemCard } from './ItemCard';
import { inventoryKeys, useEquippedItems, useInventory } from '../hooks/useInventory';

interface InventorySidebarPanelProps {
  characterId: number;
}

export function InventorySidebarPanel({ characterId }: InventorySidebarPanelProps) {
  const { data: inventory = [] } = useInventory(characterId);
  const { data: equipped = [] } = useEquippedItems(characterId);
  const queryClient = useQueryClient();

  // Equip/unequip and other item-affecting actions travel through the
  // websocket dispatcher (see WardrobePage). Invalidate the same query keys
  // on a successful result so this panel stays in sync with scene actions.
  const handleActionResult = useCallback(
    (payload: ActionResultPayload) => {
      if (!payload.success) return;
      queryClient
        .invalidateQueries({ queryKey: inventoryKeys.inventory(characterId) })
        .catch(() => {});
      queryClient
        .invalidateQueries({ queryKey: inventoryKeys.equipped(characterId) })
        .catch(() => {});
    },
    [characterId, queryClient]
  );
  useActionResult(handleActionResult);

  const equippedItemIds = useMemo(
    () => new Set(equipped.map((row) => row.item_instance)),
    [equipped]
  );

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-sm font-semibold">Inventory</h2>
        <Link to="/wardrobe" className="text-xs text-primary hover:underline">
          Manage in wardrobe
        </Link>
      </div>
      {inventory.length === 0 ? (
        <p className="text-sm italic text-muted-foreground">You aren&apos;t carrying anything.</p>
      ) : (
        <ul className="space-y-2">
          {inventory.map((item) => (
            <li key={item.id} className="relative">
              <ItemCard item={item} />
              {equippedItemIds.has(item.id) && (
                <Badge
                  variant="outline"
                  className="absolute right-2 top-2 text-[10px]"
                  data-testid={`worn-badge-${item.id}`}
                >
                  Worn
                </Badge>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

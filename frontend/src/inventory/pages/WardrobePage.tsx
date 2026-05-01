/**
 * WardrobePage — outfits + currently worn + carried inventory.
 *
 * Layout, top to bottom:
 *
 *   ┌──────────────────────────────────────────────────────────────────┐
 *   │  Wardrobe                                       [+ Save look]    │
 *   │                                                                   │
 *   │  My Outfits                                                       │
 *   │  ─────────                                                        │
 *   │  [grid of OutfitCard]                                             │
 *   │                                                                   │
 *   │  Currently Worn                              [ Undress ]          │
 *   │  ─────────────                                                    │
 *   │  [PaperDoll]    [list of ItemCard rows]                           │
 *   │                                                                   │
 *   │  Inventory                                                        │
 *   │  ─────────                                                        │
 *   │  [grid of ItemCard]                                               │
 *   └──────────────────────────────────────────────────────────────────┘
 *
 * Mutations land via two paths:
 *   - REST hooks (useCreateOutfit, useDeleteOutfit, useUpdateOutfit, etc.)
 *     handle outfit CRUD — invalidation is owned by those hooks.
 *   - Equip/unequip and apply/undress travel through the websocket action
 *     dispatcher. We listen for the `ACTION_RESULT` reply on the bus and
 *     invalidate inventory + equipped queries on success.
 */

import { useCallback, useMemo, useState } from 'react';
import { Plus, Shirt } from 'lucide-react';
import { toast } from 'sonner';
import { useQueryClient } from '@tanstack/react-query';
import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';
import { useAppSelector } from '@/store/hooks';
import { useGameSocket } from '@/hooks/useGameSocket';
import { useActionResult } from '@/hooks/actionResultBus';
import type { ActionResultPayload } from '@/hooks/types';
import { useMyRosterEntriesQuery } from '@/roster/queries';
import { ItemCard } from '../components/ItemCard';
import { ItemDetailPanel } from '../components/ItemDetailPanel';
import { OutfitCard } from '../components/OutfitCard';
import { PaperDoll, type EquippedItemDisplay } from '../components/PaperDoll';
import { SaveOutfitDialog } from '../components/SaveOutfitDialog';
import { EditOutfitDialog } from '../components/EditOutfitDialog';
import { DeleteOutfitDialog } from '../components/DeleteOutfitDialog';
import { UndressButton } from '../components/UndressButton';
import { useEquippedItems, useInventory, inventoryKeys } from '../hooks/useInventory';
import { useOutfits } from '../hooks/useOutfits';
import type { ItemInstance, Outfit } from '../types';

export function WardrobePage() {
  const activeCharacter = useAppSelector((state) => state.game.active);
  const { data: myEntries = [] } = useMyRosterEntriesQuery();

  // Resolve the active character name to its underlying ObjectDB pk. The pk
  // doubles as the CharacterSheet pk because CharacterSheet is OneToOne with
  // ObjectDB via primary_key=True.
  const activeEntry = useMemo(
    () => myEntries.find((entry) => entry.name === activeCharacter) ?? null,
    [myEntries, activeCharacter]
  );
  const characterId = activeEntry?.character_id ?? undefined;
  const characterSheetId = characterId; // Same pk by design.

  const { data: outfits = [] } = useOutfits(characterSheetId);
  const { data: inventory = [] } = useInventory(characterId);
  const { data: equipped = [] } = useEquippedItems(characterId);

  const { executeAction } = useGameSocket();
  const queryClient = useQueryClient();

  const [saveOpen, setSaveOpen] = useState(false);
  const [editingOutfit, setEditingOutfit] = useState<Outfit | null>(null);
  const [deletingOutfit, setDeletingOutfit] = useState<Outfit | null>(null);
  const [detailItem, setDetailItem] = useState<ItemInstance | null>(null);

  // -------------------------------------------------------------------------
  // WS action_result subscription
  // -------------------------------------------------------------------------

  const handleActionResult = useCallback(
    (payload: ActionResultPayload) => {
      if (payload.success) {
        if (characterId != null) {
          void queryClient.invalidateQueries({
            queryKey: inventoryKeys.inventory(characterId),
          });
          void queryClient.invalidateQueries({
            queryKey: inventoryKeys.equipped(characterId),
          });
        }
        if (payload.message) {
          toast.success(payload.message);
        }
      } else {
        toast.error(payload.message ?? 'Action failed.');
      }
    },
    [characterId, queryClient]
  );
  useActionResult(handleActionResult);

  // -------------------------------------------------------------------------
  // Derived data
  // -------------------------------------------------------------------------

  const inventoryById = useMemo(() => {
    const map = new Map<number, ItemInstance>();
    for (const item of inventory) {
      map.set(item.id, item);
    }
    return map;
  }, [inventory]);

  // Wardrobes the player can save outfits into. The backend doesn't surface
  // is_wardrobe in the list serializer (Phase A), so for now we offer the
  // full inventory and let the backend reject non-wardrobes via the
  // NotAContainer validation error. Phase B can narrow this once the field
  // is exposed in ItemTemplateList.
  const reachableWardrobes = useMemo(() => inventory, [inventory]);

  // EquippedItem from REST is a thin join row referring to an item_instance
  // by id. Hydrate against the inventory map so PaperDoll / ItemCard get
  // full ItemInstance objects.
  const equippedItems = useMemo<ItemInstance[]>(() => {
    return equipped
      .map((row) => inventoryById.get(row.item_instance))
      .filter((item): item is ItemInstance => item != null);
  }, [equipped, inventoryById]);

  const equippedDisplay = useMemo<EquippedItemDisplay[]>(() => {
    return equipped
      .map((row): EquippedItemDisplay | null => {
        const item = inventoryById.get(row.item_instance);
        if (!item) return null;
        return {
          id: item.id,
          body_region: row.body_region,
          equipment_layer: row.equipment_layer,
          display_name: item.display_name,
          display_image_url: item.display_image_url,
          quality_color_hex: item.quality_tier?.color_hex ?? '',
        };
      })
      .filter((item): item is EquippedItemDisplay => item != null);
  }, [equipped, inventoryById]);

  const equippedItemIds = useMemo(
    () => new Set(equippedItems.map((item) => item.id)),
    [equippedItems]
  );

  // -------------------------------------------------------------------------
  // Action handlers (websocket)
  // -------------------------------------------------------------------------

  const handleApplyOutfit = useCallback(
    (outfitId: number) => {
      if (!activeCharacter) return;
      executeAction(activeCharacter, 'apply_outfit', { outfit_id: outfitId });
    },
    [activeCharacter, executeAction]
  );

  const handleUndress = useCallback(() => {
    if (!activeCharacter) return;
    executeAction(activeCharacter, 'undress', {});
  }, [activeCharacter, executeAction]);

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------

  if (!activeCharacter || !characterId || !characterSheetId) {
    return (
      <div className="container mx-auto px-4 py-12">
        <h1 className="mb-4 text-3xl font-bold">Wardrobe</h1>
        <NoActiveCharacterState />
      </div>
    );
  }

  return (
    <div className="container mx-auto space-y-8 px-4 py-8">
      <header className="flex items-center justify-between gap-4">
        <h1 className="text-3xl font-bold tracking-tight">Wardrobe</h1>
        <Button onClick={() => setSaveOpen(true)} disabled={reachableWardrobes.length === 0}>
          <Plus className="mr-2 h-4 w-4" />
          Save look
        </Button>
      </header>

      <section aria-labelledby="outfits-heading" className="space-y-4">
        <SectionHeader id="outfits-heading">My Outfits</SectionHeader>
        {outfits.length === 0 ? (
          <EmptyOutfitsState
            onSaveLook={() => setSaveOpen(true)}
            hasWardrobe={reachableWardrobes.length > 0}
          />
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {outfits.map((outfit) => (
              <OutfitCard
                key={outfit.id}
                outfit={outfit}
                onWear={() => handleApplyOutfit(outfit.id)}
                onEdit={() => setEditingOutfit(outfit)}
                onDelete={() => setDeletingOutfit(outfit)}
                onItemClick={(itemId) => {
                  const item = inventoryById.get(itemId);
                  if (item) setDetailItem(item);
                }}
              />
            ))}
          </div>
        )}
      </section>

      <Separator />

      <section aria-labelledby="worn-heading" className="space-y-4">
        <div className="flex items-center justify-between gap-4">
          <SectionHeader id="worn-heading">Currently Worn</SectionHeader>
          <UndressButton equippedCount={equippedItems.length} onUndress={handleUndress} />
        </div>
        <div className="grid grid-cols-1 items-start gap-6 md:grid-cols-[280px_1fr]">
          <PaperDoll
            equipped={equippedDisplay}
            onItemClick={(itemId) => {
              const item = inventoryById.get(itemId);
              if (item) setDetailItem(item);
            }}
          />
          <div className="space-y-2">
            {equippedItems.length === 0 ? (
              <p className="italic text-muted-foreground">Nothing equipped right now.</p>
            ) : (
              equippedItems.map((item) => (
                <ItemCard key={item.id} item={item} onClick={() => setDetailItem(item)} />
              ))
            )}
          </div>
        </div>
      </section>

      <Separator />

      <section aria-labelledby="inventory-heading" className="space-y-4">
        <SectionHeader id="inventory-heading">Inventory</SectionHeader>
        {inventory.length === 0 ? (
          <p className="italic text-muted-foreground">You aren&apos;t carrying anything.</p>
        ) : (
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
            {inventory.map((item) => (
              <ItemCard key={item.id} item={item} onClick={() => setDetailItem(item)} />
            ))}
          </div>
        )}
      </section>

      <ItemDetailPanel
        item={detailItem}
        open={detailItem !== null}
        onOpenChange={(open) => {
          if (!open) setDetailItem(null);
        }}
        isEquipped={detailItem ? equippedItemIds.has(detailItem.id) : false}
      />

      <SaveOutfitDialog
        open={saveOpen}
        onOpenChange={setSaveOpen}
        characterSheetId={characterSheetId}
        reachableWardrobes={reachableWardrobes}
      />

      {editingOutfit && (
        <EditOutfitDialog
          open={editingOutfit !== null}
          onOpenChange={(open) => {
            if (!open) setEditingOutfit(null);
          }}
          outfit={editingOutfit}
          carriedItems={inventory}
        />
      )}

      {deletingOutfit && (
        <DeleteOutfitDialog
          open={deletingOutfit !== null}
          onOpenChange={(open) => {
            if (!open) setDeletingOutfit(null);
          }}
          outfit={deletingOutfit}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Local helpers
// ---------------------------------------------------------------------------

interface SectionHeaderProps {
  id: string;
  children: React.ReactNode;
}

function SectionHeader({ id, children }: SectionHeaderProps) {
  return (
    <h2 id={id} className="text-xl font-bold tracking-tight">
      {children}
    </h2>
  );
}

interface EmptyOutfitsStateProps {
  onSaveLook: () => void;
  hasWardrobe: boolean;
}

function EmptyOutfitsState({ onSaveLook, hasWardrobe }: EmptyOutfitsStateProps) {
  return (
    <div className="flex flex-col items-center justify-center rounded-lg border border-dashed px-6 py-12 text-center">
      <Shirt className="mb-4 h-12 w-12 text-muted-foreground/50" aria-hidden="true" />
      <p className="mb-1 text-muted-foreground">No saved outfits yet.</p>
      {hasWardrobe ? (
        <>
          <p className="mb-4 text-sm text-muted-foreground">
            Save your current look as your first outfit.
          </p>
          <Button onClick={onSaveLook} variant="outline" size="sm">
            <Plus className="mr-2 h-4 w-4" />
            Save look
          </Button>
        </>
      ) : (
        <p className="text-sm text-muted-foreground">
          You&apos;ll need a wardrobe item before you can save outfits.
        </p>
      )}
    </div>
  );
}

function NoActiveCharacterState() {
  return (
    <div className="flex flex-col items-center justify-center rounded-lg border border-dashed px-6 py-16 text-center">
      <Shirt className="mb-4 h-12 w-12 text-muted-foreground/50" aria-hidden="true" />
      <p className="mb-1 text-muted-foreground">Pick a character to manage their wardrobe.</p>
      <p className="text-sm text-muted-foreground">
        Switch characters from the game window to load their outfits and inventory.
      </p>
    </div>
  );
}

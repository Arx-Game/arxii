/**
 * EditOutfitDialog — modal for editing a saved outfit.
 *
 * Two sections:
 *   1. Outfit info (name + description)  — batched as a single PATCH on Save.
 *   2. Slots                              — each add/remove fires its own
 *      mutation immediately and invalidates the outfit detail query. Closing
 *      the dialog does not undo any slot mutations.
 *
 * Slot rows show the item's quality-tier color as a left-border accent to
 * match `ItemCard` / `OutfitCard` conventions.
 */

import { useEffect, useMemo, useState } from 'react';
import { Plus, X } from 'lucide-react';
import { toast } from 'sonner';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Combobox, type ComboboxItem } from '@/components/ui/combobox';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Separator } from '@/components/ui/separator';
import { Textarea } from '@/components/ui/textarea';
import { cn } from '@/lib/utils';
import { useCreateOutfitSlot, useDeleteOutfitSlot, useUpdateOutfit } from '../hooks/useOutfits';
import type { BodyRegion, EquipmentLayer, ItemInstance, Outfit, OutfitSlot } from '../types';

const MAX_NAME_LENGTH = 100;

const BODY_REGION_OPTIONS: { value: BodyRegion; label: string }[] = [
  { value: 'head', label: 'Head' },
  { value: 'face', label: 'Face' },
  { value: 'neck', label: 'Neck' },
  { value: 'shoulders', label: 'Shoulders' },
  { value: 'torso', label: 'Torso' },
  { value: 'back', label: 'Back' },
  { value: 'waist', label: 'Waist' },
  { value: 'left_arm', label: 'Left arm' },
  { value: 'right_arm', label: 'Right arm' },
  { value: 'left_hand', label: 'Left hand' },
  { value: 'right_hand', label: 'Right hand' },
  { value: 'left_leg', label: 'Left leg' },
  { value: 'right_leg', label: 'Right leg' },
  { value: 'feet', label: 'Feet' },
  { value: 'left_finger', label: 'Left finger' },
  { value: 'right_finger', label: 'Right finger' },
  { value: 'left_ear', label: 'Left ear' },
  { value: 'right_ear', label: 'Right ear' },
];

const EQUIPMENT_LAYER_OPTIONS: { value: EquipmentLayer; label: string }[] = [
  { value: 'skin', label: 'Skin' },
  { value: 'under', label: 'Under' },
  { value: 'base', label: 'Base' },
  { value: 'over', label: 'Over' },
  { value: 'outer', label: 'Outer' },
  { value: 'accessory', label: 'Accessory' },
];

const REGION_LABEL: Record<BodyRegion, string> = Object.fromEntries(
  BODY_REGION_OPTIONS.map((opt) => [opt.value, opt.label])
) as Record<BodyRegion, string>;

const LAYER_LABEL: Record<EquipmentLayer, string> = Object.fromEntries(
  EQUIPMENT_LAYER_OPTIONS.map((opt) => [opt.value, opt.label])
) as Record<EquipmentLayer, string>;

interface EditOutfitDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  outfit: Outfit;
  /** Items the character could add to a slot (typically carried inventory). */
  carriedItems: ItemInstance[];
}

export function EditOutfitDialog({
  open,
  onOpenChange,
  outfit,
  carriedItems,
}: EditOutfitDialogProps) {
  const [name, setName] = useState(outfit.name);
  const [description, setDescription] = useState(outfit.description ?? '');

  const updateMutation = useUpdateOutfit();
  const createSlotMutation = useCreateOutfitSlot();
  const deleteSlotMutation = useDeleteOutfitSlot();

  // Re-seed the form whenever the dialog opens or the outfit changes.
  useEffect(() => {
    if (open) {
      setName(outfit.name);
      setDescription(outfit.description ?? '');
    }
  }, [open, outfit.id, outfit.name, outfit.description]);

  const trimmedName = name.trim();
  const infoIsValid = trimmedName.length > 0;
  const infoIsDirty =
    trimmedName !== outfit.name.trim() || description.trim() !== (outfit.description ?? '').trim();

  function handleOpenChange(next: boolean) {
    if (updateMutation.isPending) return;
    onOpenChange(next);
  }

  function handleSaveInfo(e: React.FormEvent) {
    e.preventDefault();
    if (!infoIsValid || !infoIsDirty) return;
    updateMutation.mutate(
      {
        id: outfit.id,
        payload: {
          name: trimmedName,
          description: description.trim(),
        },
      },
      {
        onSuccess: () => {
          toast.success('Outfit updated.');
        },
        onError: (err) => {
          const message = err instanceof Error ? err.message : "Couldn't update outfit.";
          toast.error(message);
        },
      }
    );
  }

  function handleRemoveSlot(slot: OutfitSlot) {
    deleteSlotMutation.mutate(
      { id: slot.id, outfitId: outfit.id },
      {
        onSuccess: () => {
          toast.success(`Removed "${slot.item_instance.display_name}".`);
        },
        onError: (err) => {
          const message = err instanceof Error ? err.message : "Couldn't remove that piece.";
          toast.error(message);
        },
      }
    );
  }

  function handleAddSlot(payload: {
    itemInstanceId: number;
    bodyRegion: BodyRegion;
    equipmentLayer: EquipmentLayer;
  }) {
    createSlotMutation.mutate(
      {
        outfit: outfit.id,
        item_instance: payload.itemInstanceId,
        body_region: payload.bodyRegion,
        equipment_layer: payload.equipmentLayer,
      },
      {
        onSuccess: () => {
          toast.success('Piece added.');
        },
        onError: (err) => {
          const message = err instanceof Error ? err.message : "Couldn't add that piece.";
          toast.error(message);
        },
      }
    );
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Edit outfit</DialogTitle>
          <DialogDescription>
            Rename, redescribe, or rearrange the pieces in this saved outfit.
          </DialogDescription>
        </DialogHeader>

        {/* ----- Info section ----- */}
        <form onSubmit={handleSaveInfo} className="grid gap-4">
          <div className="space-y-1.5">
            <Label htmlFor="edit-outfit-name">
              Name <span className="text-destructive">*</span>
            </Label>
            <Input
              id="edit-outfit-name"
              value={name}
              onChange={(e) => setName(e.target.value.slice(0, MAX_NAME_LENGTH))}
              maxLength={MAX_NAME_LENGTH}
              required
            />
            {trimmedName.length === 0 && name.length > 0 && (
              <p className="text-xs text-destructive">Name cannot be empty.</p>
            )}
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="edit-outfit-description">Description</Label>
            <Textarea
              id="edit-outfit-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
            />
            <p className="text-xs text-muted-foreground">Supports formatting.</p>
          </div>

          <div className="flex justify-end">
            <Button
              type="submit"
              size="sm"
              disabled={!infoIsValid || !infoIsDirty || updateMutation.isPending}
            >
              {updateMutation.isPending ? 'Saving…' : 'Save'}
            </Button>
          </div>
        </form>

        <Separator />

        {/* ----- Slots section ----- */}
        <section className="grid gap-3" aria-label="Outfit slots">
          <h3 className="text-sm font-semibold">Pieces</h3>

          {outfit.slots.length === 0 ? (
            <p className="text-xs italic text-muted-foreground">No pieces yet — add one below.</p>
          ) : (
            <ul className="flex flex-col gap-2">
              {outfit.slots.map((slot) => (
                <SlotRow
                  key={slot.id}
                  slot={slot}
                  onRemove={() => handleRemoveSlot(slot)}
                  isPending={deleteSlotMutation.isPending}
                />
              ))}
            </ul>
          )}

          <AddSlotRow
            carriedItems={carriedItems}
            onAdd={handleAddSlot}
            isPending={createSlotMutation.isPending}
          />
        </section>

        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            onClick={() => handleOpenChange(false)}
            disabled={updateMutation.isPending}
          >
            Close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// Slot row
// ---------------------------------------------------------------------------

interface SlotRowProps {
  slot: OutfitSlot;
  onRemove: () => void;
  isPending: boolean;
}

function SlotRow({ slot, onRemove, isPending }: SlotRowProps) {
  const item = slot.item_instance;
  const tierColor = item.quality_tier?.color_hex || '';

  return (
    <li
      data-slot-row
      style={tierColor ? { borderLeftColor: tierColor } : undefined}
      className={cn(
        'flex items-center gap-3 rounded-md border border-l-2 border-border bg-card px-3 py-2'
      )}
    >
      <span className="min-w-0 flex-1 truncate text-sm font-medium">{item.display_name}</span>
      <span className="shrink-0 text-xs text-muted-foreground">
        {REGION_LABEL[slot.body_region]} · {LAYER_LABEL[slot.equipment_layer]}
      </span>
      <Button
        type="button"
        variant="ghost"
        size="icon"
        className="h-7 w-7 shrink-0 text-muted-foreground hover:text-destructive"
        aria-label={`Remove ${item.display_name}`}
        onClick={onRemove}
        disabled={isPending}
      >
        <X className="h-4 w-4" />
      </Button>
    </li>
  );
}

// ---------------------------------------------------------------------------
// Add slot row
// ---------------------------------------------------------------------------

interface AddSlotRowProps {
  carriedItems: ItemInstance[];
  onAdd: (payload: {
    itemInstanceId: number;
    bodyRegion: BodyRegion;
    equipmentLayer: EquipmentLayer;
  }) => void;
  isPending: boolean;
}

function AddSlotRow({ carriedItems, onAdd, isPending }: AddSlotRowProps) {
  const [itemValue, setItemValue] = useState('');
  const [bodyRegion, setBodyRegion] = useState<BodyRegion>('torso');
  const [equipmentLayer, setEquipmentLayer] = useState<EquipmentLayer>('base');

  const items: ComboboxItem[] = useMemo(
    () =>
      carriedItems.map((it) => ({
        value: String(it.id),
        label: it.display_name,
        secondaryText: it.quality_tier?.name,
      })),
    [carriedItems]
  );

  const isValid = itemValue !== '';

  function handleClick() {
    if (!isValid) return;
    onAdd({
      itemInstanceId: Number(itemValue),
      bodyRegion,
      equipmentLayer,
    });
    // Reset the item picker but keep region/layer for quick repeat adds.
    setItemValue('');
  }

  if (carriedItems.length === 0) {
    return (
      <p className="text-xs italic text-muted-foreground">No carried items available to add.</p>
    );
  }

  return (
    <div
      data-add-slot-row
      className="grid grid-cols-1 gap-2 rounded-md border border-dashed p-3 sm:grid-cols-[1fr_auto_auto_auto]"
    >
      <div>
        <Label htmlFor="add-slot-item" className="sr-only">
          Item
        </Label>
        <Combobox
          items={items}
          value={itemValue}
          onValueChange={setItemValue}
          placeholder="Pick an item…"
          searchPlaceholder="Search items…"
          emptyMessage="No matching items."
        />
      </div>

      <Select value={bodyRegion} onValueChange={(v) => setBodyRegion(v as BodyRegion)}>
        <SelectTrigger className="w-full sm:w-[140px]" aria-label="Body region">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {BODY_REGION_OPTIONS.map((opt) => (
            <SelectItem key={opt.value} value={opt.value}>
              {opt.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <Select value={equipmentLayer} onValueChange={(v) => setEquipmentLayer(v as EquipmentLayer)}>
        <SelectTrigger className="w-full sm:w-[120px]" aria-label="Equipment layer">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {EQUIPMENT_LAYER_OPTIONS.map((opt) => (
            <SelectItem key={opt.value} value={opt.value}>
              {opt.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <Button type="button" size="sm" onClick={handleClick} disabled={!isValid || isPending}>
        <Plus className="mr-1 h-3.5 w-3.5" />
        {isPending ? 'Adding…' : 'Add'}
      </Button>
    </div>
  );
}

/**
 * CommissionDialog - commission an artist's standing offer for a piece you hold (#4512).
 *
 * The form from the approved design: the offer, your item, the target (a facet or a
 * style), the commissioner's own Name and Description, a permanent "Dedicate to", and a
 * preview of what examine will read. The fee is charged whatever the roll. Writing text
 * records the commissioner as designer; leaving both blank keeps the current designer.
 * The server enforces every rule here (where text may be written, one dedication, the
 * shop); the form only shows them.
 */

import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Combobox } from '@/components/ui/combobox';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { useFacets } from '@/character-creation/queries';
import { DedicateToField, type DedicatePersona } from '@/inventory/components/DedicateToField';
import { useInventory } from '@/inventory/hooks/useInventory';
import { getStyleCatalog } from '@/magic/api';
import { FacetPicker } from '@/magic/components/FacetPicker';
import { dispatchMarketAction, type ServiceOffer } from './api';
import { examinePreview } from './commissionCredits';

const OFFER_WORK: Record<string, string> = {
  facet_attach: 'facet work',
  style_attach: 'style work',
};

interface CommissionDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  offer: ServiceOffer;
  characterId: number;
  /** The commissioner's persona name, credited as designer when they write text. */
  myName: string;
}

export function CommissionDialog({
  open,
  onOpenChange,
  offer,
  characterId,
  myName,
}: CommissionDialogProps) {
  const queryClient = useQueryClient();
  const [itemId, setItemId] = useState('');
  const [targetId, setTargetId] = useState<number | null>(null);
  const [targetName, setTargetName] = useState('');
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [dedicatee, setDedicatee] = useState<DedicatePersona | null>(null);

  const isFacetWork = offer.recipe_kind === 'facet_attach';
  const inventory = useInventory(characterId);
  const facets = useFacets();
  const styles = useQuery({
    queryKey: ['style-catalog'],
    queryFn: getStyleCatalog,
    enabled: open && !isFacetWork,
  });

  useEffect(() => {
    if (open) {
      setItemId('');
      setTargetId(null);
      setTargetName('');
      setName('');
      setDescription('');
      setDedicatee(null);
    }
  }, [open]);

  const items = inventory.data ?? [];
  const item = items.find((candidate) => String(candidate.id) === itemId);
  const canWriteName = item != null && (!item.custom_name || item.designer_is_holder);
  const canWriteDescription = item != null && (!item.custom_description || item.designer_is_holder);
  const writesText =
    (canWriteName && name.trim() !== '') || (canWriteDescription && description.trim() !== '');

  const commission = useMutation({
    mutationFn: () =>
      dispatchMarketAction(characterId, 'market_service_craft', {
        offer_id: offer.id,
        item_instance_id: item?.id,
        target_id: targetId,
        name: canWriteName ? name.trim() : '',
        description: canWriteDescription ? description.trim() : '',
        dedicate_to_id: item?.dedicated_to_name ? undefined : dedicatee?.id,
      }),
    onSuccess: (message) => {
      toast.success(message);
      void queryClient.invalidateQueries({ queryKey: ['inventory'] });
      onOpenChange(false);
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const preview = useMemo(() => {
    if (!item) return null;
    return examinePreview({
      makerName: item.crafter_name,
      designerName: item.designer_name,
      myName,
      writesText,
      madeForName: item.dedicated_to_name ?? dedicatee?.name ?? null,
      facetWorkers: item.facet_workers,
      artistName: offer.crafter_name,
    });
  }, [item, myName, writesText, dedicatee, offer.crafter_name]);

  const itemChoices = items.map((candidate) => ({
    value: String(candidate.id),
    label: candidate.display_name,
  }));
  const ready = item != null && targetId != null && !commission.isPending;

  return (
    <Dialog open={open} onOpenChange={(next) => !commission.isPending && onOpenChange(next)}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>Commission from {offer.crafter_name}&apos;s shop</DialogTitle>
          <DialogDescription>
            {offer.crafter_name}:{' '}
            {OFFER_WORK[offer.recipe_kind] ?? offer.recipe_kind.replace('_', ' ')}. Fee {offer.fee}{' '}
            coppers, charged whatever the roll. You must be standing in their shop.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          <div className="space-y-1.5">
            <Label htmlFor="commission-item">Your item</Label>
            <Combobox
              items={itemChoices}
              value={itemId}
              onValueChange={setItemId}
              placeholder={inventory.isLoading ? 'Loading your things...' : 'Choose an item...'}
              emptyMessage="You are not holding anything."
            />
            {item && (
              <div className="flex flex-wrap gap-2" data-testid="commission-item-chips">
                {item.crafter_name && (
                  <Badge variant="secondary">
                    made by {item.crafter_name}
                    {item.dedicated_to_name ? ` for ${item.dedicated_to_name}` : ''}
                  </Badge>
                )}
                {!item.custom_name && !item.custom_description && (
                  <Badge variant="outline">no name or description yet</Badge>
                )}
              </div>
            )}
          </div>

          <div className="space-y-1.5">
            <Label>{isFacetWork ? 'Facet' : 'Style'}</Label>
            {isFacetWork ? (
              <div className="flex items-center gap-2">
                <FacetPicker
                  facets={facets.data}
                  onPick={(facet) => {
                    setTargetId(facet.id);
                    setTargetName(facet.name);
                  }}
                  label={targetName || 'Choose a facet'}
                />
              </div>
            ) : (
              <Combobox
                items={(styles.data?.results ?? []).map((style) => ({
                  value: String(style.id),
                  label: style.name,
                }))}
                value={targetId ? String(targetId) : ''}
                onValueChange={(value) => setTargetId(value ? Number(value) : null)}
                placeholder="Choose a style..."
                emptyMessage="No styles."
              />
            )}
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="commission-name">Name (optional)</Label>
            <Input
              id="commission-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              disabled={item != null && !canWriteName}
              maxLength={200}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="commission-description">Description (optional, your own words)</Label>
            <Textarea
              id="commission-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              disabled={item != null && !canWriteDescription}
              rows={3}
            />
            <p className="text-xs text-muted-foreground">
              You can write these only where the item has none, or where you are already its
              designer. Writing either records you as the designer. Leaving both blank keeps the
              current designer.
            </p>
          </div>

          <DedicateToField
            idPrefix="commission"
            label="Dedicate to"
            value={dedicatee}
            onChange={setDedicatee}
            lockedTo={item?.dedicated_to_name}
            excludeName={myName}
          />

          <div className="space-y-1.5">
            <p className="text-sm font-medium">Examine will read</p>
            <p
              className="rounded-md border bg-muted/40 px-3 py-2 text-sm"
              data-testid="commission-preview"
            >
              {preview ?? 'Choose an item to see its credits.'}
            </p>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={() => commission.mutate()} disabled={!ready}>
            {commission.isPending ? 'Commissioning...' : 'Commission'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

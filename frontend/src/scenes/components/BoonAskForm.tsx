/**
 * BoonAskForm (#2540, #2540 slice 3): the structured-ask step of a boon dispatch.
 *
 * Renders after the target is picked. Five kinds:
 * - Money: RELATIVE sum tiers — options come from `fetchBoonOptions` and render as
 *   'Minor (50)' / 'Fair (200)' / 'Great (500)' against THIS target; a penniless
 *   target simply presents no money option (never an impossible ask, per the
 *   ruling).
 * - Material: a crafting category (from `material_categories`) + a sum tier —
 *   LABELS only, deliberately no coppers (asymmetric with money; no computed value
 *   is ever shown for material asks, and an empty target bucket is honestly
 *   refused at dispatch time rather than filtered out of the picker here).
 * - Held item / from a vault: the asker's pointer-known items relevant to THIS
 *   target (2026-08-27 exact-pointer ruling — `pointer_items`, filtered by
 *   `source`). An empty list renders a disabled option with neutral copy — the
 *   pointer principle made visible: you can't ask for what you don't know of.
 * - A deed: free text.
 */
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { fetchBoonOptions } from '../actionQueries';
import type { BoonAskPayload, BoonKind, BoonSumTier } from '../actionTypes';

interface BoonAskFormProps {
  targetPersonaId: number;
  targetName?: string;
  initiatorPersonaId: number;
  onConfirm: (payload: BoonAskPayload) => void;
  onCancel: () => void;
}

const SUM_TIER_LABELS: Record<BoonSumTier, string> = {
  minor: 'Minor',
  fair: 'Fair',
  great: 'Great',
};

const KIND_OPTIONS: { kind: BoonKind; label: string }[] = [
  { kind: 'money', label: 'Money' },
  { kind: 'material', label: 'Materials' },
  { kind: 'held_item', label: 'A held item' },
  { kind: 'vault_item', label: 'From a vault' },
  { kind: 'deed', label: 'A deed' },
];

export function BoonAskForm({
  targetPersonaId,
  targetName,
  initiatorPersonaId,
  onConfirm,
  onCancel,
}: BoonAskFormProps) {
  const [kind, setKind] = useState<BoonKind>('money');
  const [tier, setTier] = useState<BoonSumTier | null>(null);
  const [deedText, setDeedText] = useState('');
  const [materialCategoryId, setMaterialCategoryId] = useState<number | null>(null);
  const [itemInstanceId, setItemInstanceId] = useState<number | null>(null);

  const { data: options, isLoading } = useQuery({
    queryKey: ['boon-options', targetPersonaId, initiatorPersonaId],
    queryFn: () => fetchBoonOptions(targetPersonaId, initiatorPersonaId),
  });

  const sumOptions = options?.sum_tiers ?? [];
  const materialCategories = options?.material_categories ?? [];
  const heldItems = (options?.pointer_items ?? []).filter((item) => item.source === 'held');
  const vaultItems = (options?.pointer_items ?? []).filter((item) => item.source === 'vault');

  const moneyAvailable = sumOptions.length > 0;

  function canConfirmFor(target: BoonKind): boolean {
    switch (target) {
      case 'money':
        return tier !== null;
      case 'material':
        return materialCategoryId !== null && tier !== null;
      case 'held_item':
      case 'vault_item':
        return itemInstanceId !== null;
      case 'deed':
        return deedText.trim().length > 0;
      default:
        return false;
    }
  }

  const canConfirm = canConfirmFor(kind);

  function handleSelectKind(nextKind: BoonKind) {
    setKind(nextKind);
    setTier(null);
    setItemInstanceId(null);
  }

  function handleConfirm() {
    if (!canConfirm) return;
    switch (kind) {
      case 'money':
        onConfirm({ kind: 'money', sum_tier: tier ?? undefined });
        return;
      case 'material':
        onConfirm({
          kind: 'material',
          sum_tier: tier ?? undefined,
          material_category_id: materialCategoryId ?? undefined,
        });
        return;
      case 'held_item':
      case 'vault_item':
        onConfirm({ kind, item_instance_id: itemInstanceId ?? undefined });
        return;
      case 'deed':
        onConfirm({ kind: 'deed', deed_text: deedText.trim() });
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="w-full max-w-sm rounded-lg border bg-background p-4 shadow-lg">
        <h3 className="mb-1 text-sm font-semibold">Ask {targetName ?? 'them'} for a boon</h3>
        <p className="mb-3 text-xs text-muted-foreground">
          Name what you ask up front; they see exactly what granting costs them.
        </p>
        <div className="mb-3 flex flex-wrap gap-2">
          {KIND_OPTIONS.map((option) => (
            <Button
              key={option.kind}
              size="sm"
              variant={kind === option.kind ? 'default' : 'outline'}
              disabled={option.kind === 'money' && !moneyAvailable && !isLoading}
              onClick={() => handleSelectKind(option.kind)}
            >
              {option.label}
            </Button>
          ))}
        </div>

        {kind === 'money' && (
          <div className="mb-3 flex flex-col gap-1">
            {isLoading && <p className="text-xs text-muted-foreground">Weighing their purse…</p>}
            {!isLoading && !moneyAvailable && (
              <p className="text-xs text-muted-foreground">
                They have nothing worth asking for; ask for something else instead.
              </p>
            )}
            {sumOptions.map((option) => (
              <Button
                key={option.tier}
                size="sm"
                variant={tier === option.tier ? 'default' : 'outline'}
                className="justify-between"
                onClick={() => setTier(option.tier)}
              >
                <span>{option.label}</span>
                <span className="text-muted-foreground">{option.coppers} coppers</span>
              </Button>
            ))}
          </div>
        )}

        {kind === 'material' && (
          <div className="mb-3 flex flex-col gap-2">
            {isLoading && <p className="text-xs text-muted-foreground">Weighing their stores…</p>}
            <Select
              value={materialCategoryId !== null ? String(materialCategoryId) : undefined}
              onValueChange={(value) => setMaterialCategoryId(Number(value))}
            >
              <SelectTrigger>
                <SelectValue placeholder="Choose a crafting category…" />
              </SelectTrigger>
              <SelectContent>
                {materialCategories.map((category) => (
                  <SelectItem key={category.id} value={String(category.id)}>
                    {category.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <div className="flex flex-col gap-1">
              {(Object.keys(SUM_TIER_LABELS) as BoonSumTier[]).map((sumTier) => (
                <Button
                  key={sumTier}
                  size="sm"
                  variant={tier === sumTier ? 'default' : 'outline'}
                  onClick={() => setTier(sumTier)}
                >
                  {SUM_TIER_LABELS[sumTier]}
                </Button>
              ))}
            </div>
          </div>
        )}

        {kind === 'held_item' && (
          <div className="mb-3 flex flex-col gap-1">
            {isLoading && <p className="text-xs text-muted-foreground">Recalling what you know…</p>}
            {!isLoading && heldItems.length === 0 && (
              <Button size="sm" variant="outline" disabled>
                PLACEHOLDER: you know of nothing they hold.
              </Button>
            )}
            {heldItems.map((item) => (
              <Button
                key={item.item_instance_id}
                size="sm"
                variant={itemInstanceId === item.item_instance_id ? 'default' : 'outline'}
                onClick={() => setItemInstanceId(item.item_instance_id)}
              >
                {item.name}
              </Button>
            ))}
          </div>
        )}

        {kind === 'vault_item' && (
          <div className="mb-3 flex flex-col gap-1">
            {isLoading && <p className="text-xs text-muted-foreground">Recalling what you know…</p>}
            {!isLoading && vaultItems.length === 0 && (
              <Button size="sm" variant="outline" disabled>
                PLACEHOLDER: you know of nothing they hold.
              </Button>
            )}
            {vaultItems.map((item) => (
              <Button
                key={item.item_instance_id}
                size="sm"
                variant={itemInstanceId === item.item_instance_id ? 'default' : 'outline'}
                onClick={() => setItemInstanceId(item.item_instance_id)}
              >
                {item.name}
              </Button>
            ))}
          </div>
        )}

        {kind === 'deed' && (
          <Textarea
            className="mb-3"
            placeholder="The deed you ask of them…"
            value={deedText}
            onChange={(event) => setDeedText(event.target.value)}
            rows={3}
          />
        )}

        <div className="flex justify-end gap-2">
          <Button size="sm" variant="ghost" onClick={onCancel}>
            Cancel
          </Button>
          <Button size="sm" disabled={!canConfirm} onClick={handleConfirm}>
            Make the ask
          </Button>
        </div>
      </div>
    </div>
  );
}

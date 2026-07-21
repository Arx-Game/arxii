/**
 * BoonAskForm (#2540): the structured-ask step of a boon dispatch.
 *
 * Renders after the target is picked. Money asks are RELATIVE sum tiers — the
 * options come from `fetchBoonOptions` and render as 'Minor (50)' / 'Fair (200)' /
 * 'Great (500)' against THIS target; a penniless target simply presents no money
 * option (never an impossible ask, per the ruling). Item asks (held/vault) await
 * the item-visibility ruling and are not surfaced here yet.
 */
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { fetchBoonOptions } from '../actionQueries';
import type { BoonAskPayload, BoonSumTier } from '../actionTypes';

interface BoonAskFormProps {
  targetPersonaId: number;
  targetName?: string;
  onConfirm: (payload: BoonAskPayload) => void;
  onCancel: () => void;
}

export function BoonAskForm({
  targetPersonaId,
  targetName,
  onConfirm,
  onCancel,
}: BoonAskFormProps) {
  const [kind, setKind] = useState<'money' | 'deed'>('money');
  const [tier, setTier] = useState<BoonSumTier | null>(null);
  const [deedText, setDeedText] = useState('');

  const { data: sumOptions, isLoading } = useQuery({
    queryKey: ['boon-options', targetPersonaId],
    queryFn: () => fetchBoonOptions(targetPersonaId),
  });

  const moneyAvailable = (sumOptions?.length ?? 0) > 0;
  const canConfirm = kind === 'money' ? tier !== null : deedText.trim().length > 0;

  function handleConfirm() {
    if (!canConfirm) return;
    onConfirm(
      kind === 'money'
        ? { kind: 'money', sum_tier: tier ?? undefined }
        : { kind: 'deed', deed_text: deedText.trim() }
    );
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="w-full max-w-sm rounded-lg border bg-background p-4 shadow-lg">
        <h3 className="mb-1 text-sm font-semibold">Ask {targetName ?? 'them'} for a boon</h3>
        <p className="mb-3 text-xs text-muted-foreground">
          Name what you ask up front — they see exactly what granting costs them.
        </p>
        <div className="mb-3 flex gap-2">
          <Button
            size="sm"
            variant={kind === 'money' ? 'default' : 'outline'}
            disabled={!moneyAvailable && !isLoading}
            onClick={() => setKind('money')}
          >
            Money
          </Button>
          <Button
            size="sm"
            variant={kind === 'deed' ? 'default' : 'outline'}
            onClick={() => setKind('deed')}
          >
            A deed
          </Button>
        </div>
        {kind === 'money' && (
          <div className="mb-3 flex flex-col gap-1">
            {isLoading && <p className="text-xs text-muted-foreground">Weighing their purse…</p>}
            {!isLoading && !moneyAvailable && (
              <p className="text-xs text-muted-foreground">
                They have nothing worth asking for — ask for a deed instead.
              </p>
            )}
            {sumOptions?.map((option) => (
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

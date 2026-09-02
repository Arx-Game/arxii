/**
 * RewardLinesEditor (#3561) - a WIN branch's authored reward payouts
 * (`StakeRewardLine`): sink (money/resonance), amount, and a resonance id
 * when sink=resonance.
 *
 * Mounted only under a WIN-column `BranchColumns` card - reward lines only
 * attach to WIN resolutions (`StakeRewardLine.clean()` rejects LOSS/
 * WITHDRAWAL). "Add reward line" creates a row immediately (sink=money,
 * amount=1) the same way `BranchColumns`' "Add default branch" does; the row
 * then becomes an editable card with its own Save/Remove.
 *
 * Resonance selection is a plain numeric id input, not a name-search picker
 * - no endpoint lists the global `Resonance` catalog by id (the only
 * resonance-shaped endpoints are `character-resonances`, scoped to one
 * character's claimed set, and `resonance-grants`, an audit ledger; neither
 * fits "any resonance, paid generically to each participant"). This mirrors
 * `SubjectRefFields`' documented fallback for CharacterSheet/ItemInstance:
 * "no name-search picker exists yet; enter the numeric id directly."
 */

import { useState } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  useCreateStakeRewardLine,
  useDeleteStakeRewardLine,
  useStakeRewardLines,
  useUpdateStakeRewardLine,
} from '../../queries';
import type { StakeRewardLine, StakeRewardSink } from '../../types';

interface RewardLinesEditorProps {
  resolutionId: number;
  beatId: number;
  disabled?: boolean;
}

interface RewardLineRowProps {
  line: StakeRewardLine;
  resolutionId: number;
  beatId: number;
  disabled?: boolean;
}

function RewardLineRow({ line, resolutionId, beatId, disabled }: RewardLineRowProps) {
  const [sink, setSink] = useState<StakeRewardSink>(line.sink);
  const [amount, setAmount] = useState(String(line.amount));
  const [resonance, setResonance] = useState(line.resonance != null ? String(line.resonance) : '');
  const updateMutation = useUpdateStakeRewardLine();
  const deleteMutation = useDeleteStakeRewardLine();

  function handleSave() {
    const amountValue = Number(amount);
    if (!Number.isFinite(amountValue) || amountValue < 1) {
      toast.error('Amount must be at least 1');
      return;
    }
    updateMutation.mutate(
      {
        id: line.id,
        resolutionId,
        beatId,
        sink,
        amount: amountValue,
        resonance: sink === 'resonance' ? Number(resonance) || null : null,
      },
      {
        onSuccess: () => toast.success('Reward line saved'),
        onError: (err: unknown) =>
          toast.error(err instanceof Error ? err.message : 'Failed to save reward line'),
      }
    );
  }

  function handleRemove() {
    if (!window.confirm('Remove this reward line?')) return;
    deleteMutation.mutate(
      { id: line.id, resolutionId, beatId },
      {
        onSuccess: () => toast.success('Reward line removed'),
        onError: (err: unknown) =>
          toast.error(err instanceof Error ? err.message : 'Failed to remove reward line'),
      }
    );
  }

  return (
    <div
      className="grid grid-cols-[auto_auto_1fr_auto_auto] items-center gap-2 rounded-md border p-2"
      data-testid={`reward-line-row-${line.id}`}
    >
      <select
        className="rounded-md border bg-background px-2 py-1.5 text-xs"
        value={sink}
        onChange={(e) => setSink(e.target.value as StakeRewardSink)}
        disabled={disabled}
        data-testid={`reward-line-sink-${line.id}`}
      >
        <option value="money">Money</option>
        <option value="resonance">Resonance</option>
      </select>
      <Input
        type="number"
        min={1}
        className="w-20"
        value={amount}
        onChange={(e) => setAmount(e.target.value)}
        disabled={disabled}
        data-testid={`reward-line-amount-${line.id}`}
      />
      {sink === 'resonance' ? (
        <Input
          type="number"
          placeholder="Resonance id"
          value={resonance}
          onChange={(e) => setResonance(e.target.value)}
          disabled={disabled}
          data-testid={`reward-line-resonance-${line.id}`}
        />
      ) : (
        <span />
      )}
      <Button
        type="button"
        size="sm"
        variant="outline"
        onClick={handleSave}
        disabled={disabled || updateMutation.isPending}
        data-testid={`reward-line-save-${line.id}`}
      >
        Save
      </Button>
      <Button
        type="button"
        size="sm"
        variant="ghost"
        onClick={handleRemove}
        disabled={disabled || deleteMutation.isPending}
        data-testid={`reward-line-remove-${line.id}`}
      >
        Remove
      </Button>
    </div>
  );
}

export function RewardLinesEditor({ resolutionId, beatId, disabled }: RewardLinesEditorProps) {
  const linesQuery = useStakeRewardLines(resolutionId, true);
  const createMutation = useCreateStakeRewardLine();
  const lines = linesQuery.data?.results ?? [];

  function handleAdd() {
    createMutation.mutate(
      { beatId, resolution: resolutionId, sink: 'money', amount: 1 },
      {
        onSuccess: () => toast.success('Reward line added'),
        onError: (err: unknown) =>
          toast.error(err instanceof Error ? err.message : 'Failed to add reward line'),
      }
    );
  }

  return (
    <div className="space-y-1.5" data-testid={`reward-lines-editor-${resolutionId}`}>
      <div className="flex items-center justify-between">
        <Label className="text-xs">Reward lines</Label>
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={handleAdd}
          disabled={disabled || createMutation.isPending}
          data-testid={`reward-line-add-${resolutionId}`}
        >
          Add reward line
        </Button>
      </div>
      {lines.length === 0 && (
        <p className="text-xs text-muted-foreground">No reward lines authored yet.</p>
      )}
      {lines.map((line) => (
        <RewardLineRow
          key={line.id}
          line={line}
          resolutionId={resolutionId}
          beatId={beatId}
          disabled={disabled}
        />
      ))}
    </div>
  );
}

/**
 * RewardLinesEditor (#3561, pickers added #3566) - a WIN branch's authored
 * reward payouts (`StakeRewardLine`): sink (money/resonance/item/clue/codex),
 * amount, and the sink-matching FK (resonance id, item template, clue,
 * codex entry).
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
 *
 * ITEM/CLUE/CODEX (#3566) do have name-search pickers (`EntitySearchField`,
 * same component `SubjectRefFields` uses for its FACTION/ASSET kinds):
 * `searchItemTemplates`/`searchClues`/`searchCodexEntries` in `stories/api.ts`.
 * ITEM's amount is never author-supplied - the server pins it to the picked
 * template's value (`StakeRewardLineRequestSerializer`), so the row shows it
 * read-only and Save omits `amount` entirely for that sink. Whichever sink is
 * active sends its FK id; the other three FK fields (resonance/item_template/
 * clue/codex_entry minus the active one) go `null`, mirroring the model's
 * per-sink `clean()` rule.
 */

import { useRef, useState } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { EntitySearchField, type EntitySearchResult } from '@/components/EntitySearchField';
import {
  useCreateStakeRewardLine,
  useDeleteStakeRewardLine,
  useStakeRewardLines,
  useUpdateStakeRewardLine,
} from '../../queries';
import {
  resolveItemTemplateById,
  searchClues,
  searchCodexEntries,
  searchItemTemplates,
} from '../../api';
import type { StakeRewardLine, StakeRewardSink } from '../../types';
import { REWARD_SINK_OPTIONS } from './constants';

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
  const [itemTemplate, setItemTemplate] = useState(
    line.item_template != null ? String(line.item_template) : ''
  );
  const [clue, setClue] = useState(line.clue != null ? String(line.clue) : '');
  const [codexEntry, setCodexEntry] = useState(
    line.codex_entry != null ? String(line.codex_entry) : ''
  );
  // The picked item template's gold value (from the search result's `hint`),
  // shown as the ITEM sink's read-only amount - the server pins the real
  // payout to the template, so this is display-only, never sent on Save.
  const [itemAmountHint, setItemAmountHint] = useState<string | null>(null);
  const itemResultsRef = useRef<EntitySearchResult[]>([]);
  const updateMutation = useUpdateStakeRewardLine();
  const deleteMutation = useDeleteStakeRewardLine();

  async function searchItemTemplatesTracked(query: string) {
    const results = await searchItemTemplates(query);
    itemResultsRef.current = results;
    return results;
  }

  function handleItemChange(id: number | null) {
    setItemTemplate(id != null ? String(id) : '');
    setItemAmountHint(
      id != null ? (itemResultsRef.current.find((r) => r.id === id)?.hint ?? null) : null
    );
  }

  function handleSave() {
    if (sink === 'item' && !itemTemplate) {
      toast.error('Choose an item template');
      return;
    }
    if (sink === 'clue' && !clue) {
      toast.error('Choose a clue');
      return;
    }
    if (sink === 'codex' && !codexEntry) {
      toast.error('Choose a codex entry');
      return;
    }
    let amountValue: number | undefined;
    if (sink !== 'item') {
      amountValue = Number(amount);
      if (!Number.isFinite(amountValue) || amountValue < 1) {
        toast.error('Amount must be at least 1');
        return;
      }
    }
    updateMutation.mutate(
      {
        id: line.id,
        resolutionId,
        beatId,
        sink,
        ...(amountValue !== undefined ? { amount: amountValue } : {}),
        resonance: sink === 'resonance' ? Number(resonance) || null : null,
        item_template: sink === 'item' ? Number(itemTemplate) : null,
        clue: sink === 'clue' ? Number(clue) : null,
        codex_entry: sink === 'codex' ? Number(codexEntry) : null,
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
    <div className="space-y-2 rounded-md border p-2" data-testid={`reward-line-row-${line.id}`}>
      <div className="grid grid-cols-[auto_auto_1fr_auto_auto] items-center gap-2">
        <select
          className="rounded-md border bg-background px-2 py-1.5 text-xs"
          value={sink}
          onChange={(e) => setSink(e.target.value as StakeRewardSink)}
          disabled={disabled}
          data-testid={`reward-line-sink-${line.id}`}
        >
          {REWARD_SINK_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        {sink === 'item' ? (
          <span
            className="text-xs text-muted-foreground"
            data-testid={`reward-line-amount-${line.id}`}
          >
            Amount: {itemAmountHint ?? String(line.amount)}
          </span>
        ) : (
          <Input
            type="number"
            min={1}
            className="w-20"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            disabled={disabled}
            data-testid={`reward-line-amount-${line.id}`}
          />
        )}
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
      {sink === 'item' && (
        <div className="space-y-1">
          <EntitySearchField
            label="Item template"
            placeholder="Search item templates…"
            value={itemTemplate ? Number(itemTemplate) : null}
            onChange={handleItemChange}
            search={searchItemTemplatesTracked}
            resolveById={resolveItemTemplateById}
            disabled={disabled}
          />
          {line.item_template_name && (
            <p className="text-xs text-muted-foreground">Current: {line.item_template_name}</p>
          )}
        </div>
      )}
      {sink === 'clue' && (
        <div className="space-y-1">
          <EntitySearchField
            label="Clue"
            placeholder="Search clues…"
            value={clue ? Number(clue) : null}
            onChange={(id) => setClue(id != null ? String(id) : '')}
            search={searchClues}
            disabled={disabled}
          />
          {line.clue_name && (
            <p className="text-xs text-muted-foreground">Current: {line.clue_name}</p>
          )}
        </div>
      )}
      {sink === 'codex' && (
        <div className="space-y-1">
          <EntitySearchField
            label="Codex entry"
            placeholder="Search codex entries…"
            value={codexEntry ? Number(codexEntry) : null}
            onChange={(id) => setCodexEntry(id != null ? String(id) : '')}
            search={searchCodexEntries}
            disabled={disabled}
          />
          {line.codex_entry_name && (
            <p className="text-xs text-muted-foreground">Current: {line.codex_entry_name}</p>
          )}
        </div>
      )}
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

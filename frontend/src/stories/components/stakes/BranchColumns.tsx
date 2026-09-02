/**
 * BranchColumns (#3561) - the WIN / LOSS / WITHDRAWAL resolution branches
 * for one stake. Each column lists its authored `StakeResolution` rows
 * (plain default first, then named branches) as editable cards, plus
 * "Add default branch" (hidden once a blank-`outcome_key` row exists for
 * that column) and "Add named branch" (a select over the beat's scenario
 * option keys when the beat has a scenario graph, else free text).
 *
 * Writer fields shown per card follow `stake_resolution_payload_problems`
 * exactly (see StakeResolutionSerializer's docstring): ITEM →
 * forfeits_subject_item; NPC_FATE → sets_subject_lifecycle,
 * subject_standing_delta, npc_regard_delta, machine_match_lifecycle_state;
 * FACTION → subject_standing_delta; ASSET → transitions_subject_asset. Every
 * kind gets consequence_pool / escalates_to_risk / narrative_summary. A
 * save only ever submits the fields for the stake's own subject_kind - never
 * fields belonging to another kind.
 */

import { useState } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  useCreateStakeResolution,
  useDeleteStakeResolution,
  useStakeResolutions,
  useUpdateStakeResolution,
} from '../../queries';
import type {
  Beat,
  Stake,
  StakeEscalatesToRisk,
  StakeMachineMatchLifecycleState,
  StakeResolution,
  StakeResolutionColumn,
  StakeResolutionUpdateBody,
  StakeSetsSubjectLifecycle,
} from '../../types';
import { ConsequencePoolPicker } from '../ConsequencePoolPicker';
import { RewardLinesEditor } from './RewardLinesEditor';
import {
  ASSET_TRANSITION_OPTIONS,
  COLUMN_LABELS,
  COLUMN_OPTIONS,
  LIFECYCLE_STATE_OPTIONS,
  RISK_LADDER,
  riskLabel,
} from './constants';

// ---------------------------------------------------------------------------
// One branch card
// ---------------------------------------------------------------------------

interface BranchCardProps {
  resolution: StakeResolution;
  stake: Stake;
  beatId: number;
  disabled?: boolean;
}

function BranchCard({ resolution, stake, beatId, disabled }: BranchCardProps) {
  const [consequencePool, setConsequencePool] = useState<number | null>(
    resolution.consequence_pool ?? null
  );
  const [escalatesToRisk, setEscalatesToRisk] = useState<StakeEscalatesToRisk>(
    resolution.escalates_to_risk ?? ''
  );
  const [narrativeSummary, setNarrativeSummary] = useState(resolution.narrative_summary ?? '');
  const [forfeitsItem, setForfeitsItem] = useState(resolution.forfeits_subject_item ?? false);
  const [standingDelta, setStandingDelta] = useState(
    String(resolution.subject_standing_delta ?? 0)
  );
  const [regardDelta, setRegardDelta] = useState(String(resolution.npc_regard_delta ?? 0));
  const [setsLifecycle, setSetsLifecycle] = useState<StakeSetsSubjectLifecycle>(
    resolution.sets_subject_lifecycle ?? ''
  );
  const [machineMatch, setMachineMatch] = useState<StakeMachineMatchLifecycleState>(
    resolution.machine_match_lifecycle_state ?? ''
  );
  const [assetTransition, setAssetTransition] = useState(
    resolution.transitions_subject_asset ?? ''
  );

  const updateMutation = useUpdateStakeResolution();
  const deleteMutation = useDeleteStakeResolution();

  function writerFieldsForKind(): Partial<StakeResolutionUpdateBody> {
    switch (stake.subject_kind) {
      case 'item':
        return { forfeits_subject_item: forfeitsItem };
      case 'npc_fate':
        return {
          sets_subject_lifecycle: setsLifecycle,
          subject_standing_delta: Number(standingDelta) || 0,
          npc_regard_delta: Number(regardDelta) || 0,
          machine_match_lifecycle_state: machineMatch,
        };
      case 'faction':
        return { subject_standing_delta: Number(standingDelta) || 0 };
      case 'asset':
        return { transitions_subject_asset: assetTransition };
      default:
        return {};
    }
  }

  function handleSave() {
    updateMutation.mutate(
      {
        id: resolution.id,
        stakeId: stake.id,
        beatId,
        consequence_pool: consequencePool,
        escalates_to_risk: escalatesToRisk,
        narrative_summary: narrativeSummary,
        ...writerFieldsForKind(),
      },
      {
        onSuccess: () => toast.success('Branch saved'),
        onError: (err: unknown) =>
          toast.error(err instanceof Error ? err.message : 'Failed to save branch'),
      }
    );
  }

  function handleDelete() {
    if (!window.confirm('Delete this branch?')) return;
    deleteMutation.mutate(
      { id: resolution.id, stakeId: stake.id, beatId },
      {
        onSuccess: () => toast.success('Branch deleted'),
        onError: (err: unknown) =>
          toast.error(err instanceof Error ? err.message : 'Failed to delete branch'),
      }
    );
  }

  return (
    <div className="space-y-2 rounded-md border p-2" data-testid={`branch-card-${resolution.id}`}>
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium">{resolution.outcome_key || 'Default branch'}</span>
        <Button
          type="button"
          size="sm"
          variant="ghost"
          onClick={handleDelete}
          disabled={disabled || deleteMutation.isPending}
          data-testid={`branch-delete-${resolution.id}`}
        >
          Delete
        </Button>
      </div>

      <ConsequencePoolPicker
        value={consequencePool}
        onChange={setConsequencePool}
        label="Consequence pool"
        disabled={disabled}
      />

      <div className="space-y-1">
        <Label className="text-xs">Escalates to risk</Label>
        <select
          className="w-full rounded-md border bg-background px-2 py-1.5 text-xs"
          value={escalatesToRisk}
          onChange={(e) => setEscalatesToRisk(e.target.value as StakeEscalatesToRisk)}
          disabled={disabled}
          data-testid={`branch-escalates-${resolution.id}`}
        >
          <option value="">None declared</option>
          {RISK_LADDER.map((r) => (
            <option key={r} value={r}>
              {riskLabel(r)}
            </option>
          ))}
        </select>
      </div>

      <div className="space-y-1">
        <Label className="text-xs">Narrative summary</Label>
        <Textarea
          value={narrativeSummary}
          onChange={(e) => setNarrativeSummary(e.target.value)}
          disabled={disabled}
          rows={2}
          data-testid={`branch-narrative-${resolution.id}`}
        />
      </div>

      {stake.subject_kind === 'item' && (
        <label className="flex items-center gap-2 text-xs">
          <input
            type="checkbox"
            checked={forfeitsItem}
            onChange={(e) => setForfeitsItem(e.target.checked)}
            disabled={disabled}
            data-testid={`branch-forfeits-item-${resolution.id}`}
          />
          Forfeits the subject item
        </label>
      )}

      {stake.subject_kind === 'npc_fate' && (
        <div className="space-y-2">
          <div className="space-y-1">
            <Label className="text-xs">Sets lifecycle</Label>
            <select
              className="w-full rounded-md border bg-background px-2 py-1.5 text-xs"
              value={setsLifecycle}
              onChange={(e) => setSetsLifecycle(e.target.value as StakeSetsSubjectLifecycle)}
              disabled={disabled}
              data-testid={`branch-sets-lifecycle-${resolution.id}`}
            >
              <option value="">No lifecycle change</option>
              {LIFECYCLE_STATE_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-1">
            <Label className="text-xs">Standing delta</Label>
            <Input
              type="number"
              value={standingDelta}
              onChange={(e) => setStandingDelta(e.target.value)}
              disabled={disabled}
              data-testid={`branch-standing-delta-${resolution.id}`}
            />
          </div>
          <div className="space-y-1">
            <Label className="text-xs">NPC regard delta</Label>
            <Input
              type="number"
              value={regardDelta}
              onChange={(e) => setRegardDelta(e.target.value)}
              disabled={disabled}
              data-testid={`branch-regard-delta-${resolution.id}`}
            />
          </div>
          <div className="space-y-1">
            <Label className="text-xs">Machine match lifecycle</Label>
            <select
              className="w-full rounded-md border bg-background px-2 py-1.5 text-xs"
              value={machineMatch}
              onChange={(e) => setMachineMatch(e.target.value as StakeMachineMatchLifecycleState)}
              disabled={disabled}
              data-testid={`branch-machine-match-${resolution.id}`}
            >
              <option value="">No machine match</option>
              {LIFECYCLE_STATE_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </div>
        </div>
      )}

      {stake.subject_kind === 'faction' && (
        <div className="space-y-1">
          <Label className="text-xs">Standing delta</Label>
          <Input
            type="number"
            value={standingDelta}
            onChange={(e) => setStandingDelta(e.target.value)}
            disabled={disabled}
            data-testid={`branch-standing-delta-${resolution.id}`}
          />
        </div>
      )}

      {stake.subject_kind === 'asset' && (
        <div className="space-y-1">
          <Label className="text-xs">Transitions the subject asset</Label>
          <select
            className="w-full rounded-md border bg-background px-2 py-1.5 text-xs"
            value={assetTransition}
            onChange={(e) => setAssetTransition(e.target.value)}
            disabled={disabled}
            data-testid={`branch-asset-transition-${resolution.id}`}
          >
            <option value="">No direct transition</option>
            {ASSET_TRANSITION_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>
      )}

      {resolution.column === 'win' && (
        <RewardLinesEditor resolutionId={resolution.id} beatId={beatId} disabled={disabled} />
      )}

      <Button
        type="button"
        size="sm"
        onClick={handleSave}
        disabled={disabled || updateMutation.isPending}
        data-testid={`branch-save-${resolution.id}`}
      >
        Save
      </Button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// One column (WIN / LOSS / WITHDRAWAL)
// ---------------------------------------------------------------------------

interface BranchColumnProps {
  column: StakeResolutionColumn;
  resolutions: StakeResolution[];
  stake: Stake;
  beat: Beat;
  disabled?: boolean;
}

function BranchColumn({ column, resolutions, stake, beat, disabled }: BranchColumnProps) {
  const [addingNamed, setAddingNamed] = useState(false);
  const [namedKey, setNamedKey] = useState('');
  const createMutation = useCreateStakeResolution();

  const hasDefaultBranch = resolutions.some((r) => !r.outcome_key);
  const optionKeys = beat.scenario?.option_keys ?? [];

  function addDefaultBranch() {
    createMutation.mutate(
      { beatId: beat.id, stake: stake.id, column, outcome_key: '' },
      {
        onSuccess: () => toast.success('Branch added'),
        onError: (err: unknown) =>
          toast.error(err instanceof Error ? err.message : 'Failed to add branch'),
      }
    );
  }

  const trimmedNamedKey = namedKey.trim();
  const isDuplicateNamedKey = resolutions.some((r) => r.outcome_key === trimmedNamedKey);

  function confirmNamedBranch() {
    const key = trimmedNamedKey;
    if (!key || isDuplicateNamedKey) return;
    createMutation.mutate(
      { beatId: beat.id, stake: stake.id, column, outcome_key: key },
      {
        onSuccess: () => {
          toast.success('Branch added');
          setAddingNamed(false);
          setNamedKey('');
        },
        onError: (err: unknown) =>
          toast.error(err instanceof Error ? err.message : 'Failed to add branch'),
      }
    );
  }

  return (
    <div className="min-w-0 flex-1 space-y-2" data-testid={`branch-column-${column}`}>
      <h4 className="text-xs font-semibold uppercase text-muted-foreground">
        {COLUMN_LABELS[column]}
      </h4>
      {resolutions.length === 0 && (
        <p className="text-xs text-muted-foreground">No branches authored yet.</p>
      )}
      {resolutions.map((r) => (
        <BranchCard key={r.id} resolution={r} stake={stake} beatId={beat.id} disabled={disabled} />
      ))}
      <div className="flex flex-wrap items-center gap-2">
        {!hasDefaultBranch && (
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={addDefaultBranch}
            disabled={disabled || createMutation.isPending}
            data-testid={`add-default-branch-${column}`}
          >
            Add default branch
          </Button>
        )}
        {!addingNamed ? (
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => setAddingNamed(true)}
            disabled={disabled}
            data-testid={`add-named-branch-${column}`}
          >
            Add named branch
          </Button>
        ) : (
          <div className="flex items-center gap-1">
            {optionKeys.length > 0 ? (
              <select
                className="rounded-md border bg-background px-2 py-1.5 text-xs"
                value={namedKey}
                onChange={(e) => setNamedKey(e.target.value)}
                data-testid={`named-branch-key-select-${column}`}
              >
                <option value="">Scenario option…</option>
                {optionKeys.map((k) => (
                  <option key={k} value={k}>
                    {k}
                  </option>
                ))}
              </select>
            ) : (
              <Input
                className="w-40"
                value={namedKey}
                onChange={(e) => setNamedKey(e.target.value)}
                placeholder="branch_key"
                data-testid={`named-branch-key-input-${column}`}
              />
            )}
            <Button
              type="button"
              size="sm"
              onClick={confirmNamedBranch}
              disabled={!trimmedNamedKey || isDuplicateNamedKey || createMutation.isPending}
              data-testid={`confirm-named-branch-${column}`}
            >
              Add
            </Button>
            {isDuplicateNamedKey && (
              <p
                className="text-xs text-destructive"
                data-testid={`named-branch-key-duplicate-${column}`}
              >
                That key is already authored on this column
              </p>
            )}
            <Button
              type="button"
              size="sm"
              variant="ghost"
              onClick={() => {
                setAddingNamed(false);
                setNamedKey('');
              }}
            >
              Cancel
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// All three columns
// ---------------------------------------------------------------------------

interface BranchColumnsProps {
  stake: Stake;
  beat: Beat;
  disabled?: boolean;
}

export function BranchColumns({ stake, beat, disabled }: BranchColumnsProps) {
  const resolutionsQuery = useStakeResolutions(stake.id, true);
  const resolutions = resolutionsQuery.data?.results ?? [];

  return (
    <div className="flex flex-col gap-3 sm:flex-row" data-testid={`branch-columns-${stake.id}`}>
      {COLUMN_OPTIONS.map((opt) => (
        <BranchColumn
          key={opt.value}
          column={opt.value}
          resolutions={resolutions.filter((r) => r.column === opt.value)}
          stake={stake}
          beat={beat}
          disabled={disabled}
        />
      ))}
    </div>
  );
}

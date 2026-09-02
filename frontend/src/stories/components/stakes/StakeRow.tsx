/**
 * StakeRow (#3561) - one authored `Stake` on the beat: its template (shown
 * read-only - templates denormalize onto the stake at create time and are
 * never re-picked), subject reference (`SubjectRefFields`), severity, and
 * player-facing summary, with Save/Delete. Renders `BranchColumns` beneath
 * for the stake's WIN/LOSS/WITHDRAWAL resolution branches.
 */

import { useState } from 'react';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useDeleteStake, useStakeTemplates, useUpdateStake } from '../../queries';
import type { Beat, Stake, StakeSeverity } from '../../types';
import { emptySubjectRef, SubjectRefFields, type SubjectRefValue } from '../SubjectRefFields';
import { BranchColumns } from './BranchColumns';
import { SEVERITY_OPTIONS } from './constants';

interface StakeRowProps {
  stake: Stake;
  beat: Beat;
  disabled?: boolean;
}

function subjectRefFromStake(stake: Stake): SubjectRefValue {
  return {
    ...emptySubjectRef(stake.subject_kind ?? 'custom'),
    subject_sheet: stake.subject_sheet ?? null,
    subject_item: stake.subject_item ?? null,
    subject_society: stake.subject_society ?? null,
    subject_organization: stake.subject_organization ?? null,
    subject_asset: stake.subject_asset ?? null,
    subject_label: stake.subject_label ?? '',
  };
}

export function StakeRow({ stake, beat, disabled }: StakeRowProps) {
  const [subjectRef, setSubjectRef] = useState<SubjectRefValue>(() => subjectRefFromStake(stake));
  const [severity, setSeverity] = useState<StakeSeverity>(stake.severity ?? 1);
  const [playerSummary, setPlayerSummary] = useState(stake.player_summary);

  const { data: templatesData } = useStakeTemplates();
  const template = templatesData?.results.find((t) => t.id === stake.template);

  const updateMutation = useUpdateStake();
  const deleteMutation = useDeleteStake();

  function handleSave() {
    updateMutation.mutate(
      {
        id: stake.id,
        beatId: beat.id,
        subject_kind: subjectRef.subject_kind,
        subject_sheet: subjectRef.subject_sheet,
        subject_item: subjectRef.subject_item,
        subject_society: subjectRef.subject_society,
        subject_organization: subjectRef.subject_organization,
        subject_asset: subjectRef.subject_asset,
        subject_label: subjectRef.subject_label,
        severity,
        player_summary: playerSummary,
      },
      {
        onSuccess: () => toast.success('Stake saved'),
        onError: (err: unknown) =>
          toast.error(err instanceof Error ? err.message : 'Failed to save stake'),
      }
    );
  }

  function handleDelete() {
    if (!window.confirm('Delete this stake and its branches?')) return;
    deleteMutation.mutate(
      { id: stake.id, beatId: beat.id },
      {
        onSuccess: () => toast.success('Stake deleted'),
        onError: (err: unknown) =>
          toast.error(err instanceof Error ? err.message : 'Failed to delete stake'),
      }
    );
  }

  return (
    <li className="space-y-3 rounded-md border bg-card p-3" data-testid={`stake-row-${stake.id}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Badge variant="outline" data-testid={`stake-template-${stake.id}`}>
          {template ? template.name : 'Custom stake'}
        </Badge>
        <Button
          type="button"
          size="sm"
          variant="ghost"
          onClick={handleDelete}
          disabled={disabled || deleteMutation.isPending}
          data-testid={`stake-delete-${stake.id}`}
        >
          Delete stake
        </Button>
      </div>

      <SubjectRefFields value={subjectRef} onChange={setSubjectRef} disabled={disabled} />

      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1">
          <Label className="text-xs">Severity</Label>
          <select
            className="w-full rounded-md border bg-background px-2 py-1.5 text-sm"
            value={severity}
            onChange={(e) => setSeverity(Number(e.target.value) as StakeSeverity)}
            disabled={disabled}
            data-testid={`stake-severity-${stake.id}`}
          >
            {SEVERITY_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="space-y-1">
        <Label className="text-xs">Player-facing summary</Label>
        <Input
          value={playerSummary}
          onChange={(e) => setPlayerSummary(e.target.value)}
          disabled={disabled}
          data-testid={`stake-player-summary-${stake.id}`}
        />
      </div>

      <Button
        type="button"
        size="sm"
        onClick={handleSave}
        disabled={disabled || updateMutation.isPending}
        data-testid={`stake-save-${stake.id}`}
      >
        Save stake
      </Button>

      <BranchColumns stake={stake} beat={beat} disabled={disabled} />
    </li>
  );
}

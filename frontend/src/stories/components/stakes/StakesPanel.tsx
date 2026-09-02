/**
 * StakesPanel (#3561) - the stakes-contract editor for one beat: header
 * (declared risk, target level, readiness verdict + lock via
 * `ReadinessStrip`), the beat's `Stake` rows (`StakeRow`, each carrying its
 * own `BranchColumns`), and "Add stake" (template-banded to the beat's
 * declared risk, or a custom stake when the caller is staff or their
 * `GMProfileMine.allow_custom_stakes` is set).
 *
 * Mounted in `BeatFormDialog` (edit mode, after the Scenario section) and in
 * `StoryAuthorTree.BeatRowAuthor` (behind a collapsed-by-default "Stakes"
 * chevron) - both pass the same `Beat`, so this component owns no
 * beat-fetching of its own.
 */

import { useState } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useGMProfileMine } from '@/gm/queries';
import { useAccount } from '@/store/hooks';
import { useCreateStake, useOpenBeatActivation, useStakeTemplates, useStakes } from '../../queries';
import type { Beat, StakeRequestBody, StakeSeverity, StakeTemplate } from '../../types';
import { SUBJECT_KIND_LABELS } from '../SubjectRefFields';
import { ReadinessStrip } from './ReadinessStrip';
import { riskIndex, riskLabel, SEVERITY_OPTIONS } from './constants';
import { StakeRow } from './StakeRow';

// ---------------------------------------------------------------------------
// Add-stake mini forms
// ---------------------------------------------------------------------------

interface AddFromTemplateFormProps {
  beatId: number;
  templates: StakeTemplate[];
  onDone: () => void;
}

function AddFromTemplateForm({ beatId, templates, onDone }: AddFromTemplateFormProps) {
  const [templateId, setTemplateId] = useState('');
  const [playerSummary, setPlayerSummary] = useState('');
  const createMutation = useCreateStake();

  function handleCreate() {
    const body: StakeRequestBody = {
      beat: beatId,
      template: Number(templateId),
      player_summary: playerSummary.trim(),
    };
    createMutation.mutate(
      { beatId, ...body },
      {
        onSuccess: () => {
          toast.success('Stake added');
          onDone();
        },
        onError: () => toast.error('Failed to add stake'),
      }
    );
  }

  const canSubmit = templateId !== '' && playerSummary.trim() !== '' && !createMutation.isPending;

  return (
    <div
      className="space-y-2 rounded-md border border-dashed p-3"
      data-testid="stakes-add-template-form"
    >
      <select
        className="w-full rounded-md border bg-background px-2 py-1.5 text-sm"
        value={templateId}
        onChange={(e) => setTemplateId(e.target.value)}
        data-testid="stakes-add-template-select"
      >
        <option value="">Select a template…</option>
        {templates.map((t) => (
          <option key={t.id} value={t.id}>
            {t.name}
          </option>
        ))}
      </select>
      <Input
        value={playerSummary}
        onChange={(e) => setPlayerSummary(e.target.value)}
        placeholder="Player-facing summary"
        data-testid="stakes-add-template-summary"
      />
      <div className="flex gap-2">
        <Button
          type="button"
          size="sm"
          onClick={handleCreate}
          disabled={!canSubmit}
          data-testid="stakes-add-template-confirm"
        >
          Add stake
        </Button>
        <Button type="button" size="sm" variant="ghost" onClick={onDone}>
          Cancel
        </Button>
      </div>
    </div>
  );
}

interface AddCustomFormProps {
  beatId: number;
  onDone: () => void;
}

function AddCustomForm({ beatId, onDone }: AddCustomFormProps) {
  const [subjectKind, setSubjectKind] =
    useState<StakeRequestBody['subject_kind']>('personal_jeopardy');
  const [severity, setSeverity] = useState<StakeSeverity>(1);
  const [playerSummary, setPlayerSummary] = useState('');
  const createMutation = useCreateStake();

  function handleCreate() {
    const body: StakeRequestBody = {
      beat: beatId,
      template: null,
      subject_kind: subjectKind,
      severity,
      player_summary: playerSummary.trim(),
    };
    createMutation.mutate(
      { beatId, ...body },
      {
        onSuccess: () => {
          toast.success('Custom stake added');
          onDone();
        },
        onError: () => toast.error('Failed to add stake'),
      }
    );
  }

  const canSubmit = playerSummary.trim() !== '' && !createMutation.isPending;

  return (
    <div
      className="space-y-2 rounded-md border border-dashed p-3"
      data-testid="stakes-add-custom-form"
    >
      <select
        className="w-full rounded-md border bg-background px-2 py-1.5 text-sm"
        value={subjectKind}
        onChange={(e) => setSubjectKind(e.target.value as StakeRequestBody['subject_kind'])}
        data-testid="stakes-add-custom-subject-kind"
      >
        {(Object.keys(SUBJECT_KIND_LABELS) as (keyof typeof SUBJECT_KIND_LABELS)[]).map((kind) => (
          <option key={kind} value={kind}>
            {SUBJECT_KIND_LABELS[kind]}
          </option>
        ))}
      </select>
      <select
        className="w-full rounded-md border bg-background px-2 py-1.5 text-sm"
        value={severity}
        onChange={(e) => setSeverity(Number(e.target.value) as StakeSeverity)}
        data-testid="stakes-add-custom-severity"
      >
        {SEVERITY_OPTIONS.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
      <Input
        value={playerSummary}
        onChange={(e) => setPlayerSummary(e.target.value)}
        placeholder="Player-facing summary"
        data-testid="stakes-add-custom-summary"
      />
      <div className="flex gap-2">
        <Button
          type="button"
          size="sm"
          onClick={handleCreate}
          disabled={!canSubmit}
          data-testid="stakes-add-custom-confirm"
        >
          Add custom stake
        </Button>
        <Button type="button" size="sm" variant="ghost" onClick={onDone}>
          Cancel
        </Button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Panel
// ---------------------------------------------------------------------------

interface StakesPanelProps {
  beat: Beat;
}

export function StakesPanel({ beat }: StakesPanelProps) {
  const beatId = beat.id;
  const stakesQuery = useStakes(beatId, true);
  const activationQuery = useOpenBeatActivation(beatId, true);
  const templatesQuery = useStakeTemplates();
  const account = useAccount();
  const isStaff = account?.is_staff ?? false;
  const gmProfileQuery = useGMProfileMine();
  const canAddCustom = isStaff || (gmProfileQuery.data?.allow_custom_stakes ?? false);

  const [addMode, setAddMode] = useState<'none' | 'template' | 'custom'>('none');

  const isLocked = (activationQuery.data?.[0] ?? null) != null;

  const beatRiskIndex = riskIndex(beat.risk);
  const eligibleTemplates = (templatesQuery.data?.results ?? []).filter(
    (t) => riskIndex(t.min_risk) <= beatRiskIndex && beatRiskIndex <= riskIndex(t.max_risk)
  );

  const stakes = stakesQuery.data?.results ?? [];

  return (
    <div className="space-y-3 rounded-md border p-3" data-testid="stakes-panel">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold">Stakes</h3>
        <div className="text-xs text-muted-foreground" data-testid="stakes-panel-header">
          Declared risk: {riskLabel(beat.risk)} · Target level: {beat.target_level ?? ' - '}
        </div>
      </div>

      <ReadinessStrip beatId={beatId} />

      {!isLocked && (
        <div className="space-y-2">
          {addMode === 'none' && (
            <div className="flex flex-wrap gap-2">
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() => setAddMode('template')}
                data-testid="stakes-add-btn"
              >
                Add stake
              </Button>
              {canAddCustom && (
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={() => setAddMode('custom')}
                  data-testid="stakes-add-custom-btn"
                >
                  Custom stake
                </Button>
              )}
            </div>
          )}
          {addMode === 'template' && (
            <AddFromTemplateForm
              beatId={beatId}
              templates={eligibleTemplates}
              onDone={() => setAddMode('none')}
            />
          )}
          {addMode === 'custom' && (
            <AddCustomForm beatId={beatId} onDone={() => setAddMode('none')} />
          )}
        </div>
      )}

      <ul className="space-y-3" data-testid="stakes-list">
        {stakes.length === 0 && (
          <li className="text-xs text-muted-foreground" data-testid="stakes-empty">
            No stakes declared yet.
          </li>
        )}
        {stakes.map((stake) => (
          <StakeRow key={stake.id} stake={stake} beat={beat} disabled={isLocked} />
        ))}
      </ul>
    </div>
  );
}

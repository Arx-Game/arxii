/**
 * ActionDeclarationCard — shared core action-declaration UI.
 *
 * Used by both scenes and combat. Contract per spec §4 of
 * docs/superpowers/specs/2026-05-23-unified-combat-ui-design.md.
 *
 * Props note: the card takes `characterId` (Evennia ObjectDB pk), NOT
 * `characterSheetId`. The caller handles the characterSheet → ObjectDB pk
 * mapping. This keeps the card thin and consistent with the existing
 * fetchAvailableActions(characterId) API in scenes/actionQueries.ts.
 *
 * Deferred (not in this phase):
 * - `onCommitPulls` — wired by the combat panel in Phase 7 (CombatTurnPanel).
 * - `onSubmit` — wired by the combat panel in Phase 7.
 * - Real target picker with combatants list — deferred to Phase 7.
 * - ThreadPullPicker embedding — deferred to Phase 6.4.
 */

import { useQuery } from '@tanstack/react-query';
import { cn } from '@/lib/utils';
import { fetchAvailableActions } from '@/scenes/actionQueries';
import type { PlayerAction } from '@/scenes/actionTypes';
import { useTechnique } from '@/magic/queries';
import type { ActionContext, EffortLevel } from './types';

// ---------------------------------------------------------------------------
// Public props contract
// ---------------------------------------------------------------------------

export interface ActionDeclarationCardProps {
  /** Evennia ObjectDB pk for the character. NOT characterSheetId. */
  characterId: number;
  actionContext: ActionContext;
  onContextChange: (next: ActionContext) => void;
  readOnly?: boolean;
}

// ---------------------------------------------------------------------------
// Effort pills sub-component
// ---------------------------------------------------------------------------

const EFFORT_LABELS: Record<EffortLevel, string> = {
  VERY_LOW: 'Very Low',
  LOW: 'Low',
  MEDIUM: 'Medium',
  HIGH: 'High',
  VERY_HIGH: 'Very High',
};

const EFFORT_ORDER: EffortLevel[] = ['VERY_LOW', 'LOW', 'MEDIUM', 'HIGH', 'VERY_HIGH'];

interface EffortSelectorProps {
  selected: EffortLevel;
  onChange: (effort: EffortLevel) => void;
  disabled?: boolean;
}

function EffortSelector({ selected, onChange, disabled }: EffortSelectorProps) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {EFFORT_ORDER.map((level) => (
        <button
          key={level}
          type="button"
          disabled={disabled}
          onClick={() => onChange(level)}
          className={cn(
            'rounded-full border px-2.5 py-0.5 text-xs font-medium transition-colors',
            'disabled:cursor-not-allowed disabled:opacity-50',
            selected === level
              ? 'border-primary bg-primary text-primary-foreground'
              : 'border-border bg-background text-muted-foreground hover:border-primary/50 hover:text-foreground'
          )}
        >
          {EFFORT_LABELS[level]}
        </button>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Technique picker sub-component
// ---------------------------------------------------------------------------

interface TechniquePickerProps {
  techniques: PlayerAction[];
  selectedId: number | undefined;
  onSelect: (techniqueId: number) => void;
  disabled?: boolean;
}

function TechniquePicker({ techniques, selectedId, onSelect, disabled }: TechniquePickerProps) {
  if (techniques.length === 0) {
    return (
      <p className="text-xs text-muted-foreground">No techniques available.</p>
    );
  }

  return (
    <div className="flex flex-wrap gap-1.5">
      {techniques.map((action) => {
        const techId = action.ref.technique_id;
        if (techId === null) return null;
        const isSelected = selectedId === techId;
        return (
          <button
            key={techId}
            type="button"
            disabled={disabled || !action.prerequisite_met}
            onClick={() => onSelect(techId)}
            title={
              action.prerequisite_reasons.length > 0
                ? action.prerequisite_reasons.join('; ')
                : action.description
            }
            className={cn(
              'rounded border px-2.5 py-1 text-xs font-medium transition-colors text-left',
              'disabled:cursor-not-allowed disabled:opacity-50',
              isSelected
                ? 'border-primary bg-primary/10 text-primary'
                : 'border-border bg-background text-foreground hover:border-primary/50'
            )}
          >
            {action.display_name}
          </button>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Target picker sub-component (placeholder — real picker wired in Phase 7)
// ---------------------------------------------------------------------------

interface TargetPickerProps {
  targetId: number | undefined;
  targetKind: ActionContext['targetKind'];
  onTargetChange: (targetKind: ActionContext['targetKind'], targetId: number | undefined) => void;
  disabled?: boolean;
}

function TargetPicker({ targetId, targetKind, onTargetChange, disabled }: TargetPickerProps) {
  // Phase 5 placeholder — kind select only.
  // Real combatant-list target picker is wired in Phase 7.
  return (
    <div className="flex items-center gap-2">
      <select
        disabled={disabled}
        value={targetKind ?? ''}
        onChange={(e) => {
          const kind = e.target.value as ActionContext['targetKind'];
          onTargetChange(kind || undefined, targetId);
        }}
        className="rounded border border-border bg-background px-2 py-1 text-xs text-foreground"
      >
        <option value="">— no target —</option>
        <option value="opponent">Opponent</option>
        <option value="ally">Ally</option>
        <option value="social">Social</option>
        <option value="self">Self</option>
      </select>
      {targetKind && targetKind !== 'self' && (
        <span className="text-xs text-muted-foreground">(target picker: Phase 7)</span>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// I/C chip sub-component
// ---------------------------------------------------------------------------

interface ICChipProps {
  intensity: number;
  control: number;
}

function ICChip({ intensity, control }: ICChipProps) {
  const isOverburn = intensity > control;

  return (
    <span
      data-testid="ic-chip"
      title={
        isOverburn
          ? 'Intensity exceeds Control — overburn risk'
          : 'Control meets or exceeds Intensity — comfortable cast'
      }
      className={cn(
        'inline-flex items-center rounded border px-2 py-0.5 text-xs font-mono',
        isOverburn
          ? 'bg-amber-500/20 border-amber-500/40 text-amber-300'
          : 'bg-muted border-border text-muted-foreground'
      )}
    >
      I:{intensity} / C:{control}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Cost preview sub-component
//
// This is intentionally informational and computed client-side.
// Real cost is computed server-side at cast time. The formula here is
// a heuristic:
//   - control >= intensity  → 0 anima (comfortable)
//   - intensity > control   → ~anima_cost anima (overburn risk — server confirms)
// ---------------------------------------------------------------------------

interface CostPreviewProps {
  intensity: number;
  control: number;
  animaCost: number;
}

function CostPreview({ intensity, control, animaCost }: CostPreviewProps) {
  const isOverburn = intensity > control;

  if (isOverburn) {
    return (
      <p className="text-xs text-amber-400">
        Cost: ~{animaCost} anima · (overburn risk — server confirms at cast)
      </p>
    );
  }

  return (
    <p className="text-xs text-muted-foreground">
      Cost: 0 anima · (Control &ge; Intensity, comfortable)
    </p>
  );
}

// ---------------------------------------------------------------------------
// Section wrapper
// ---------------------------------------------------------------------------

function Section({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        {label}
      </p>
      {children}
    </div>
  );
}

// ---------------------------------------------------------------------------
// ActionDeclarationCard
// ---------------------------------------------------------------------------

export function ActionDeclarationCard({
  characterId,
  actionContext,
  onContextChange,
  readOnly = false,
}: ActionDeclarationCardProps) {
  // Fetch available techniques for this character.
  // The API returns all PlayerActions; we filter to those with a technique_id
  // so pure-combat actions without a technique are excluded.
  const { data, isLoading } = useQuery({
    queryKey: ['available-actions', characterId],
    queryFn: () => fetchAvailableActions(characterId),
    enabled: characterId > 0,
  });

  // Fetch technique detail for I/C chip and cost preview (Task 5.3).
  // Route: GET /api/magic/techniques/<id>/ via useTechnique (magic/queries.ts).
  const { data: techniqueDetail } = useTechnique(actionContext.techniqueId);

  const techniques = (data?.results ?? []).filter((a) => a.ref.technique_id !== null);

  function handleTechniqueSelect(techniqueId: number) {
    onContextChange({ ...actionContext, techniqueId });
  }

  function handleTargetChange(
    targetKind: ActionContext['targetKind'],
    targetId: number | undefined
  ) {
    onContextChange({ ...actionContext, targetKind, targetId });
  }

  function handleEffortChange(effort: EffortLevel) {
    onContextChange({ ...actionContext, effort });
  }

  const hasTechnique = actionContext.techniqueId !== undefined;

  return (
    <div className="rounded-lg border border-border bg-card p-4 shadow-sm space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold capitalize">
          {actionContext.slot.replace(/-/g, ' ')}
        </h3>
        {/* I/C chip — shown when technique detail is loaded */}
        {techniqueDetail && (
          <ICChip
            intensity={techniqueDetail.intensity ?? 0}
            control={techniqueDetail.control ?? 0}
          />
        )}
      </div>

      {/* Technique section */}
      <Section label="Technique">
        {isLoading ? (
          <p className="text-xs text-muted-foreground">Loading techniques...</p>
        ) : !hasTechnique ? (
          <div className="space-y-2">
            <p className="text-xs text-muted-foreground italic">Pick a technique</p>
            <TechniquePicker
              techniques={techniques}
              selectedId={actionContext.techniqueId}
              onSelect={handleTechniqueSelect}
              disabled={readOnly}
            />
          </div>
        ) : (
          <TechniquePicker
            techniques={techniques}
            selectedId={actionContext.techniqueId}
            onSelect={handleTechniqueSelect}
            disabled={readOnly}
          />
        )}
      </Section>

      {/* Target section */}
      <Section label="Target">
        <TargetPicker
          targetId={actionContext.targetId}
          targetKind={actionContext.targetKind}
          onTargetChange={handleTargetChange}
          disabled={readOnly}
        />
      </Section>

      {/* Effort section */}
      <Section label="Effort">
        <EffortSelector
          selected={actionContext.effort}
          onChange={handleEffortChange}
          disabled={readOnly}
        />
      </Section>

      {/* Cost section */}
      <Section label="Cost">
        {techniqueDetail ? (
          <CostPreview
            intensity={techniqueDetail.intensity ?? 0}
            control={techniqueDetail.control ?? 0}
            animaCost={techniqueDetail.anima_cost}
          />
        ) : (
          <p className="text-xs text-muted-foreground">
            {hasTechnique ? 'Loading cost...' : '— select a technique first —'}
          </p>
        )}
      </Section>

      {/* Thread pulls placeholder — wired in Phase 6.4 */}
      <Section label="Thread Pulls">
        <p className="text-xs text-muted-foreground">
          Thread pull picker — Phase 6
        </p>
      </Section>
    </div>
  );
}

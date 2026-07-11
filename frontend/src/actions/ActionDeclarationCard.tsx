/**
 * ActionDeclarationCard — shared core action-declaration UI.
 *
 * Used by both scenes and combat. Contract per spec §4 of
 * docs/superpowers/specs/2026-05-23-unified-combat-ui-design.md.
 *
 * Props:
 * - characterId     — Evennia ObjectDB pk. NOT characterSheetId. Used with
 *                     fetchAvailableActions (scenes/actionQueries).
 * - characterSheetId — CharacterSheet pk. Used by the applicable-pulls API
 *                      (POST /api/magic/applicable-pulls/). The two IDs are
 *                      different objects; the parent supplies both. Phase 7
 *                      CombatTurnPanel knows both.
 *
 * Deferred (not in this phase):
 * - `onCommitPulls` — wired by the combat panel in Phase 7 (CombatTurnPanel).
 * - `onSubmit` — wired by the combat panel in Phase 7.
 * - Real target picker with combatants list — deferred to Phase 7.
 */

import { useEffect, useMemo, useState } from 'react';
import { useQuery as useTQQuery } from '@tanstack/react-query';
import { cn } from '@/lib/utils';
import { fetchAvailableActions } from '@/scenes/actionQueries';
import type { PlayerAction } from '@/scenes/actionTypes';
import { useTechnique, useCharacterResonances } from '@/magic/queries';
import { ThreadPullPicker } from '@/magic/components/threads/ThreadPullPicker';
import type { ApplicablePullsRequest } from '@/magic/types';
import type {
  ActionContext,
  CastPosition,
  EffortLevel,
  PositionTargetShape,
  TargetOption,
} from './types';
import type { PositionAdjacencyItem, PositionNode } from '@/combat/types';
import { isPositionReachable, isTargetReachable } from '@/combat/reach';

// ---------------------------------------------------------------------------
// Public props contract
// ---------------------------------------------------------------------------

export interface ActionDeclarationCardProps {
  /** Evennia ObjectDB pk for the character. NOT characterSheetId. */
  characterId: number;
  /**
   * CharacterSheet pk. Used by the applicable-pulls API. Different from
   * characterId (ObjectDB). Phase 7 CombatTurnPanel supplies both.
   */
  characterSheetId: number;
  actionContext: ActionContext;
  onContextChange: (next: ActionContext) => void;
  readOnly?: boolean;
  /**
   * Selectable combatants for the focused-target picker (#1001a). When provided
   * (combat), the picker lists real opponents/allies; when omitted (scenes), it
   * falls back to the kind-only selector.
   */
  targets?: TargetOption[];
  /**
   * Reach pre-filter props (#532). When all three are provided, the target
   * picker disables options that are out of range for the selected technique.
   */
  /** The selected technique's reach constraint ("same" | "adjacent" | "any" | null). */
  reach?: string | null;
  /** The acting participant's current position PK, or null if unplaced. */
  actorPositionId?: number | null;
  /** The encounter's position adjacency graph. */
  positionAdjacency?: PositionAdjacencyItem[];
  /**
   * Cast-time position-targeting props (#2206). When the selected technique's
   * `positionTargetShape` is "single" or "pair", the card renders a Position
   * group. `positions` is the same position-node source `CombatTacticalMap`
   * uses (`EncounterDetail.position_nodes`), threaded down by the caller.
   */
  /** The selected technique's cast-time position-targeting shape. */
  positionTargetShape?: PositionTargetShape;
  /** The encounter's position nodes (id/name/kind) to pick from. */
  positions?: PositionNode[];
  /** Lifted position selection state (owned by the caller, e.g. YourTurn). */
  castPosition?: CastPosition;
  /** Setter for the lifted position selection state. */
  onCastPositionChange?: (next: CastPosition) => void;
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
    return <p className="text-xs text-muted-foreground">No techniques available.</p>;
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
              'rounded border px-2.5 py-1 text-left text-xs font-medium transition-colors',
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
  /** Real combatants (combat). When undefined, render the kind-only fallback. */
  targets?: TargetOption[];
  /** Reach pre-filter — technique's reach constraint (#532). */
  reach?: string | null;
  /** Actor's current position PK for the reach check. */
  actorPositionId?: number | null;
  /** Room's position adjacency graph for the reach check. */
  positionAdjacency?: PositionAdjacencyItem[];
}

/** Kind-only fallback selector used in scenes (no combatant list available). */
function TargetKindSelect({ targetId, targetKind, onTargetChange, disabled }: TargetPickerProps) {
  return (
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
  );
}

/** One combatant button. */
function TargetButton({
  option,
  selected,
  disabled,
  title,
  onSelect,
}: {
  option: TargetOption;
  selected: boolean;
  disabled?: boolean;
  title?: string;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      title={title}
      onClick={onSelect}
      className={cn(
        'rounded border px-2.5 py-1 text-left text-xs font-medium transition-colors',
        'disabled:cursor-not-allowed disabled:opacity-50',
        selected
          ? 'border-primary bg-primary/10 text-primary'
          : 'border-border bg-background text-foreground hover:border-primary/50'
      )}
    >
      {option.name}
    </button>
  );
}

function TargetPicker(props: TargetPickerProps) {
  const {
    targetId,
    targetKind,
    onTargetChange,
    disabled,
    targets,
    reach,
    actorPositionId,
    positionAdjacency,
  } = props;

  // Scenes: no combatant list → kind-only selector.
  if (targets === undefined) {
    return (
      <div className="flex items-center gap-2">
        <TargetKindSelect {...props} />
      </div>
    );
  }

  const opponents = targets.filter((t) => t.kind === 'opponent');
  const allies = targets.filter((t) => t.kind === 'ally');
  const hasSelection = targetKind !== undefined && targetId !== undefined;

  const renderGroup = (label: string, options: TargetOption[]) =>
    options.length > 0 && (
      <div className="space-y-1">
        <p className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</p>
        <div className="flex flex-wrap gap-1.5">
          {options.map((option) => {
            // Reach pre-filter (#532): disable targets out of range for the selected technique.
            const reachable = isTargetReachable(
              reach,
              actorPositionId,
              option.positionId,
              positionAdjacency ?? []
            );
            const isDisabledByReach = !reachable;
            return (
              <TargetButton
                key={`${option.kind}-${option.id}`}
                option={option}
                selected={targetKind === option.kind && targetId === option.id}
                disabled={disabled || isDisabledByReach}
                title={isDisabledByReach ? 'Out of reach for this technique' : undefined}
                onSelect={() => onTargetChange(option.kind, option.id)}
              />
            );
          })}
        </div>
      </div>
    );

  return (
    <div className="space-y-2" data-testid="combatant-target-picker">
      {targets.length === 0 ? (
        <p className="text-xs text-muted-foreground">No targets available.</p>
      ) : (
        <>
          {renderGroup('Opponents', opponents)}
          {renderGroup('Allies', allies)}
          <button
            type="button"
            disabled={disabled || !hasSelection}
            onClick={() => onTargetChange(undefined, undefined)}
            className={cn(
              'text-[11px] underline-offset-2 transition-colors',
              hasSelection
                ? 'text-muted-foreground hover:text-foreground hover:underline'
                : 'cursor-not-allowed text-muted-foreground/50'
            )}
          >
            Clear target
          </button>
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Position picker sub-component (#2206) — cast-time position targeting
// ---------------------------------------------------------------------------

/** One position button — position name + kind label, styled like TargetButton. */
function PositionSlotButton({
  node,
  selected,
  disabled,
  title,
  onSelect,
}: {
  node: PositionNode;
  selected: boolean;
  disabled?: boolean;
  title?: string;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      title={title}
      onClick={onSelect}
      className={cn(
        'rounded border px-2.5 py-1 text-left text-xs font-medium transition-colors',
        'disabled:cursor-not-allowed disabled:opacity-50',
        selected
          ? 'border-primary bg-primary/10 text-primary'
          : 'border-border bg-background text-foreground hover:border-primary/50'
      )}
    >
      {node.name} <span className="text-[10px] text-muted-foreground">({node.kind})</span>
    </button>
  );
}

interface PositionPickerProps {
  shape: PositionTargetShape;
  positions: PositionNode[];
  castPosition: CastPosition;
  onCastPositionChange: (next: CastPosition) => void;
  disabled?: boolean;
  /** Reach pre-filter — technique's reach constraint (#532), single-shape only. */
  reach?: string | null;
  actorPositionId?: number | null;
  positionAdjacency?: PositionAdjacencyItem[];
}

function PositionPicker({
  shape,
  positions,
  castPosition,
  onCastPositionChange,
  disabled,
  reach,
  actorPositionId,
  positionAdjacency,
}: PositionPickerProps) {
  if (positions.length === 0) {
    return <p className="text-xs text-muted-foreground">No positions available.</p>;
  }

  if (shape === 'single') {
    const hasSelection = castPosition.destinationId !== undefined;
    return (
      <div className="space-y-1" data-testid="position-picker-single">
        <div className="flex flex-wrap gap-1.5">
          {positions.map((node) => {
            // Reach pre-filter (#2206): disable positions out of range for the technique.
            const reachable = isPositionReachable(
              reach,
              actorPositionId,
              node.id,
              positionAdjacency ?? []
            );
            const isDisabledByReach = !reachable;
            return (
              <PositionSlotButton
                key={node.id}
                node={node}
                selected={castPosition.destinationId === node.id}
                disabled={disabled || isDisabledByReach}
                title={isDisabledByReach ? 'Out of reach for this technique' : undefined}
                onSelect={() => onCastPositionChange({ ...castPosition, destinationId: node.id })}
              />
            );
          })}
        </div>
        <button
          type="button"
          disabled={disabled || !hasSelection}
          onClick={() => onCastPositionChange({ ...castPosition, destinationId: undefined })}
          className={cn(
            'text-[11px] underline-offset-2 transition-colors',
            hasSelection
              ? 'text-muted-foreground hover:text-foreground hover:underline'
              : 'cursor-not-allowed text-muted-foreground/50'
          )}
        >
          Clear position
        </button>
      </div>
    );
  }

  // shape === 'pair' — two labelled slots (A/B); no reach pre-filter (#2206 brief §Step 2).
  // A barrier needs two different endpoints — disable whichever node is already picked
  // in the OTHER slot so the pair can't collapse onto a single position.
  const renderSlot = (
    label: string,
    selectedId: number | undefined,
    otherSelectedId: number | undefined,
    onPick: (id: number) => void
  ) => (
    <div className="space-y-1">
      <p className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</p>
      <div className="flex flex-wrap gap-1.5">
        {positions.map((node) => {
          const isDisabledByPair = otherSelectedId !== undefined && node.id === otherSelectedId;
          return (
            <PositionSlotButton
              key={node.id}
              node={node}
              selected={selectedId === node.id}
              disabled={disabled || isDisabledByPair}
              title={isDisabledByPair ? 'Already selected as the other endpoint' : undefined}
              onSelect={() => onPick(node.id)}
            />
          );
        })}
      </div>
    </div>
  );

  const hasSelection = castPosition.pairA !== undefined || castPosition.pairB !== undefined;

  return (
    <div className="space-y-2" data-testid="position-picker-pair">
      {renderSlot('Position A', castPosition.pairA, castPosition.pairB, (id) =>
        onCastPositionChange({ ...castPosition, pairA: id })
      )}
      {renderSlot('Position B', castPosition.pairB, castPosition.pairA, (id) =>
        onCastPositionChange({ ...castPosition, pairB: id })
      )}
      <button
        type="button"
        disabled={disabled || !hasSelection}
        onClick={() =>
          onCastPositionChange({ ...castPosition, pairA: undefined, pairB: undefined })
        }
        className={cn(
          'text-[11px] underline-offset-2 transition-colors',
          hasSelection
            ? 'text-muted-foreground hover:text-foreground hover:underline'
            : 'cursor-not-allowed text-muted-foreground/50'
        )}
      >
        Clear positions
      </button>
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
        'inline-flex items-center rounded border px-2 py-0.5 font-mono text-xs',
        isOverburn
          ? 'border-amber-500/40 bg-amber-500/20 text-amber-300'
          : 'border-border bg-muted text-muted-foreground'
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
      <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{label}</p>
      {children}
    </div>
  );
}

// ---------------------------------------------------------------------------
// ActionDeclarationCard
// ---------------------------------------------------------------------------

export function ActionDeclarationCard({
  characterId,
  characterSheetId,
  actionContext,
  onContextChange,
  readOnly = false,
  targets,
  reach,
  actorPositionId,
  positionAdjacency,
  positionTargetShape,
  positions,
  castPosition,
  onCastPositionChange,
}: ActionDeclarationCardProps) {
  // Fetch available techniques for this character.
  const { data, isLoading } = useTQQuery({
    queryKey: ['available-actions', characterId],
    queryFn: () => fetchAvailableActions(characterId),
    enabled: characterId > 0,
  });

  // Fetch technique detail for I/C chip and cost preview.
  const {
    data: techniqueDetail,
    isLoading: techniqueLoading,
    isError: techniqueError,
  } = useTechnique(actionContext.techniqueId);

  const techniques = (data?.results ?? []).filter((a) => a.ref.technique_id !== null);

  // Thread pull state (local — Phase 7 can lift or add onPullsChange prop)
  const [selectedPulls, setSelectedPulls] = useState<Record<number, 0 | 1 | 2 | 3>>({});
  const [showInapplicable, setShowInapplicable] = useState(false);
  const [revertNotice, setRevertNotice] = useState<string | null>(null);

  // Resonance balances — used by ThreadPullPicker to display unaffordable-tier tooltips.
  const { data: resonances } = useCharacterResonances(
    characterSheetId > 0 ? characterSheetId : undefined
  );
  const balanceByResonanceId = useMemo<Record<number, number>>(() => {
    if (!resonances) return {};
    return Object.fromEntries(resonances.map((cr) => [cr.resonance, cr.balance ?? 0]));
  }, [resonances]);

  // Build applicable-pulls context from current card state.
  //
  // Id-space note (#1001a): in combat (`targets` provided) actionContext.targetId
  // is the dispatch PK (CombatOpponent / CombatParticipant), which is NOT the
  // applicable-pulls id-space. The pulls API wants the opponent's ObjectDB pk
  // (target_object_id) — carried on the selected TargetOption.objectId — and a
  // persona id for allies, which the combat list does not carry (left null; no
  // regression — combat ally pulls were never scoped). In scenes (no `targets`)
  // the legacy mapping stands: targetId is the object/persona id directly.
  const pullsContext = useMemo<ApplicablePullsRequest | null>(() => {
    if (characterSheetId <= 0) return null;
    const isCombatTargeting = targets !== undefined;
    const selectedTarget = targets?.find(
      (t) => t.kind === actionContext.targetKind && t.id === actionContext.targetId
    );

    let targetObjectId: number | null = null;
    let targetPersonaId: number | null = null;
    if (isCombatTargeting) {
      targetObjectId =
        actionContext.targetKind === 'opponent' ? (selectedTarget?.objectId ?? null) : null;
      // Combat allies carry no persona id; opponent scoping uses target_object_id.
    } else {
      targetObjectId =
        actionContext.targetKind === 'opponent' ? (actionContext.targetId ?? null) : null;
      targetPersonaId =
        actionContext.targetKind === 'social' || actionContext.targetKind === 'ally'
          ? (actionContext.targetId ?? null)
          : null;
    }

    return {
      character_sheet_id: characterSheetId,
      technique_id: actionContext.techniqueId ?? null,
      target_persona_id: targetPersonaId,
      target_object_id: targetObjectId,
      scene_id: null, // wired in Phase 7 when CombatTurnPanel passes scene context
      effect_type_id: null,
    };
  }, [
    characterSheetId,
    actionContext.techniqueId,
    actionContext.targetKind,
    actionContext.targetId,
    targets,
  ]);

  // Clear revert notice after 4 seconds
  useEffect(() => {
    if (!revertNotice) return;
    const t = setTimeout(() => setRevertNotice(null), 4_000);
    return () => clearTimeout(t);
  }, [revertNotice]);

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
    <div className="space-y-4 rounded-lg border border-border bg-card p-4 shadow-sm">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold capitalize">
          {actionContext.slot.replace(/-/g, ' ')}
        </h3>
        {/* I/C chip — shown when technique detail is loaded; hidden on error */}
        {techniqueDetail && !techniqueError && (
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
            <p className="text-xs italic text-muted-foreground">Pick a technique</p>
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
          targets={targets}
          reach={reach}
          actorPositionId={actorPositionId}
          positionAdjacency={positionAdjacency}
        />
      </Section>

      {/* Position section (#2206) — only when the selected technique targets positions */}
      {hasTechnique && positionTargetShape != null && positionTargetShape !== 'none' && (
        <Section label="Position">
          <PositionPicker
            shape={positionTargetShape}
            positions={positions ?? []}
            castPosition={castPosition ?? {}}
            onCastPositionChange={onCastPositionChange ?? (() => {})}
            disabled={readOnly}
            reach={reach}
            actorPositionId={actorPositionId}
            positionAdjacency={positionAdjacency}
          />
        </Section>
      )}

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
        ) : techniqueError ? (
          <p className="text-xs text-muted-foreground">Cost unavailable</p>
        ) : (
          <p className="text-xs text-muted-foreground">
            {hasTechnique && techniqueLoading ? 'Loading cost...' : '— select a technique first —'}
          </p>
        )}
      </Section>

      {/* Thread pulls section — Phase 6.4 */}
      <Section label="Thread Pulls">
        {/* Auto-revert notice */}
        {revertNotice && (
          <p className="mb-1 text-xs text-amber-400" data-testid="revert-notice">
            {revertNotice}
          </p>
        )}
        {pullsContext !== null ? (
          <ThreadPullPicker
            characterSheetId={characterSheetId}
            actionContext={pullsContext}
            selectedPulls={selectedPulls}
            onPullsChange={setSelectedPulls}
            showInapplicable={showInapplicable}
            onToggleInapplicable={setShowInapplicable}
            onAutoRevertNotice={setRevertNotice}
            balanceByResonanceId={balanceByResonanceId}
          />
        ) : (
          <p className="text-xs text-muted-foreground">— no sheet context —</p>
        )}
      </Section>
    </div>
  );
}

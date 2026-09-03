/**
 * YourTurn — the "Your Turn" section of the combat right rail.
 *
 * Hosts the focused slot + passive slots, combo upgrade row, clash contribution
 * subsection, and the Submit declarations button.
 *
 * Slot composition rules (spec §6, plan Task 7.1):
 * - One focused-slot ActionDeclarationCard.
 * - Passive cards ONLY for categories NOT used by focused. When focused=Physical,
 *   render Social + Mental passives. No disabled-placeholder for the focused category.
 *
 * Phase 7 of the unified-combat-ui plan.
 */

import { useEffect, useMemo, useRef, useState } from 'react';
import type { SetStateAction } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { cn } from '@/lib/utils';
import { ActionDeclarationCard } from '@/actions/ActionDeclarationCard';
import type {
  ActionContext,
  ActionSlot,
  CastPosition,
  EffortLevel,
  PositionTargetShape,
  TargetOption,
} from '@/actions/types';
import type { PlayerAction, SoulfrayWarningData } from '@/scenes/actionTypes';
import { MovementActions } from '../components/MovementActions';
import { PendingAttacks } from '../components/PendingAttacks';
import { SoulfrayAcceptGate } from '../components/SoulfrayAcceptGate';
import { FuryDeclaration } from '../components/FuryDeclaration';
import { ThreadPullDialog, type PullSelection } from '@/magic/components/threads/ThreadPullDialog';
import { useCharacterAnima } from '@/magic/queries';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { useInventory } from '@/inventory/hooks/useInventory';
import {
  combatKeys,
  invalidateConsequenceOutcomes,
  useAvailableCombos,
  useCoverMutation,
  useDispatchPlayerAction,
  useFleeMutation,
  useGuardMutation,
  useRegistryDispatch,
  useUpgradeCombo,
} from '../queries';
import { isDispatchFailure } from '../types';
import type {
  AvailableCombo,
  DispatchActionRequest,
  DispatchResult,
  EncounterDetail,
  Participant,
  PositionNode,
  RoundActionTyped,
} from '../types';
import type { components } from '@/generated/api';

type ConditionInstance = components['schemas']['ConditionInstance'];

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface YourTurnProps {
  encounterId: number;
  characterId: number;
  characterSheetId: number;
  /** Current encounter round number — resets the submitted state when it changes. */
  roundNumber: number;
  /** Available PlayerActions for the character — caller filters COMBAT backend. */
  availableActions: PlayerAction[];
  readOnly?: boolean;
  /** Strain slider max — typically ParticipantSerializer.available_strain.
   *  Falls back to 10 if not provided. */
  availableStrain?: number | null;
  /**
   * Full encounter detail — used to gate flee/cover controls on declaring phase
   * and to resolve ally names for the cover picker. Optional so callers that
   * don't have encounter data yet can still render the slot composition.
   */
  encounter?: EncounterDetail | null;
  /**
   * Cast-time position selection, controlled by the caller (#2206). CombatTurnPanel/
   * CombatRail lift this above the rail tabs so the tactical-map tab can share
   * it with this panel. Optional and falls back to local `useState` when the caller
   * doesn't provide it (e.g. tests rendering YourTurn standalone) — unlike
   * ActionDeclarationCard's castPosition prop, which has no such local-state
   * fallback and simply no-ops without a caller-supplied setter.
   */
  castPosition?: CastPosition;
  onCastPositionChange?: (next: CastPosition) => void;
  /**
   * Reports the currently-selected focused technique's position-targeting shape
   * to the caller (#2206) — lets a sibling tab (the tactical map) know whether
   * map-click position-picking should be active, even after this panel unmounts
   * (rail tabs unmount their inactive TabsContent).
   */
  onPositionShapeChange?: (shape: PositionTargetShape) => void;
}

// ---------------------------------------------------------------------------
// Passive slot categories
// ---------------------------------------------------------------------------

const PASSIVE_SLOTS: ActionSlot[] = ['passive-physical', 'passive-social', 'passive-mental'];

/**
 * Map the UI's uppercase EffortLevel to the backend's lowercase
 * fatigue.EffortLevel TextChoices value (the value stored on CombatRoundAction
 * and keyed in EFFORT_CHECK_MODIFIER). The COMBAT dispatch requires
 * `effort_level` in kwargs on every declaration (focused + each passive) or it
 * rejects with UNKNOWN_ACTION_REF. The UI's 'VERY_HIGH' tier maps to the
 * backend's 'extreme'.
 */
const EFFORT_TO_BACKEND: Record<EffortLevel, string> = {
  VERY_LOW: 'very_low',
  LOW: 'low',
  MEDIUM: 'medium',
  HIGH: 'high',
  VERY_HIGH: 'extreme',
};

/**
 * Display labels for `PlayerAction.protective_flavor` (#2207) — mirrors
 * PROTECTIVE_FLAVOR_BARRIER/_BLINK/_REDIRECT in
 * world/magic/services/targeting.py. Purely cosmetic (Guard technique picker).
 */
const PROTECTIVE_FLAVOR_LABELS: Record<string, string> = {
  barrier: 'Barrier',
  blink: 'Blink',
  redirect: 'Redirect',
};

/** Sentinel Select values — Radix Select disallows an empty-string item value. */
const GUARD_ANYONE_VALUE = '__anyone__';
const GUARD_NO_TECHNIQUE_VALUE = '__none__';
/** Redirect destination sentinel (#2210) — the universal fallback; also the
 *  default when the picker's kwargs are omitted entirely. */
const GUARD_DESTINATION_AWAY = '__away__';
/** Redirect destination Select value prefixes (#2210) — parsed in handleGuard. */
const GUARD_DESTINATION_OPPONENT_PREFIX = 'opponent:';
const GUARD_DESTINATION_OBJECT_PREFIX = 'object:';

/**
 * Use Item target sentinel/prefixes (#3381) — mirrors the guard-redirect
 * sentinel pattern above. `on_use_target_kind` isn't exposed on any item
 * serializer (verified against code — the anti-reinvention ledger's premise
 * that it was already serialized turned out false), so rather than add a
 * backend field this always offers an optional self/ally/opponent target and
 * lets the backend accept or reject it, the same backend-trusting philosophy
 * the spec already applies to Charge/Joust (Decision 4).
 */
const USE_ITEM_TARGET_SELF = '__self__';
const USE_ITEM_TARGET_ALLY_PREFIX = 'ally:';
const USE_ITEM_TARGET_OPPONENT_PREFIX = 'opponent:';
/** Condition name gating the Mounted Maneuvers mini-panel (#3381, #1843). */
const MOUNTED_CONDITION_NAME = 'Mounted';

/**
 * Derive the focused slot's category from the selected technique's
 * `action_category` (#614), surfaced on the PlayerAction descriptor. The
 * matching passive slot is hidden (spec §6). Returns null when no focused
 * technique is selected or its category is unset.
 */
function resolveFocusedCategory(
  context: ActionContext,
  availableActions: PlayerAction[]
): ActionSlot | null {
  if (context.techniqueId === undefined) return null;
  const selected = availableActions.find((a) => a.ref.technique_id === context.techniqueId);
  if (!selected?.action_category) return null;
  return `passive-${selected.action_category}` as ActionSlot;
}

/**
 * Return the passive slot names that should be rendered given the focused
 * category. The focused category's passive slot is hidden entirely (spec §6).
 */
function passiveSlotsToRender(focusedCategory: ActionSlot | null): ActionSlot[] {
  if (focusedCategory === null) return PASSIVE_SLOTS;
  return PASSIVE_SLOTS.filter((s) => s !== focusedCategory);
}

// ---------------------------------------------------------------------------
// Initial context factory
// ---------------------------------------------------------------------------

function initialContext(slot: ActionSlot): ActionContext {
  return {
    slot,
    effort: 'MEDIUM',
    strainCommitment: 0,
  };
}

// ---------------------------------------------------------------------------
// Round-scoped state (#2423 finding 4) — consolidated into one object so a
// round advance resets it WHOLESALE, making "forgot to reset one atom" bugs
// structurally impossible (previously selectedClashRef/strainByClash/
// focusedContext/passiveContexts/submitError survived a round advance and
// leaked a stale clash selection into the next round's submit).
// ---------------------------------------------------------------------------

interface RoundScopedState {
  focusedContext: ActionContext;
  passiveContexts: Partial<Record<ActionSlot, ActionContext>>;
  selectedClashRef: PlayerAction['ref'] | null;
  strainByClash: Record<number, number>;
  submitted: boolean;
  submitError: string | null;
  pullDialogOpen: boolean;
  selectedPull: PullSelection | null;
  soulfrayAccepted: boolean;
  furyTierId: number | null;
  furyAnchorId: number | null;
  coverAllyId: string;
  maneuverError: string | null;
  guardAllyId: string;
  guardTechniqueId: string;
  guardDestination: string;
  /** Guardian's consent (#3573) to keep a technique-guardian's ward alive
   *  past zero anima by drawing on Soulfray. Reset to false whenever
   *  guardTechniqueId switches to mundane (no protective technique). */
  guardSoulfrayAccepted: boolean;
  // #3381 additions — rally/succor ally pickers, use-item declaration,
  // charge/joust mini-panel. Each control's own error is tracked separately
  // from `maneuverError` since these render outside the Maneuvers cluster
  // (except rally/succor, which share it, mirroring Cover).
  rallyAllyId: string;
  succorAllyId: string;
  useItemInstanceId: string;
  useItemTargetValue: string;
  useItemError: string | null;
  chargeOpponentId: string;
  chargeTechniqueId: string;
  chargeError: string | null;
  joustTechniqueId: string;
  joustError: string | null;
}

/** Everything a new round must wipe — reset WHOLESALE so a missed atom is impossible (#2423). */
function initialRoundState(): RoundScopedState {
  return {
    focusedContext: initialContext('focused'),
    passiveContexts: {
      'passive-physical': initialContext('passive-physical'),
      'passive-social': initialContext('passive-social'),
      'passive-mental': initialContext('passive-mental'),
    },
    selectedClashRef: null,
    strainByClash: {},
    submitted: false,
    submitError: null,
    pullDialogOpen: false,
    selectedPull: null,
    soulfrayAccepted: false,
    furyTierId: null,
    furyAnchorId: null,
    coverAllyId: '',
    maneuverError: null,
    guardAllyId: GUARD_ANYONE_VALUE,
    guardTechniqueId: GUARD_NO_TECHNIQUE_VALUE,
    guardDestination: GUARD_DESTINATION_AWAY,
    guardSoulfrayAccepted: false,
    rallyAllyId: '',
    succorAllyId: '',
    useItemInstanceId: '',
    useItemTargetValue: USE_ITEM_TARGET_SELF,
    useItemError: null,
    chargeOpponentId: '',
    chargeTechniqueId: '',
    chargeError: null,
    joustTechniqueId: '',
    joustError: null,
  };
}

// ---------------------------------------------------------------------------
// Dispatch-job builders (extracted from handleSubmit to flatten its branching)
// ---------------------------------------------------------------------------

type DispatchFn = (params: DispatchActionRequest) => Promise<DispatchResult>;

type DispatchJob = () => Promise<DispatchResult>;

/**
 * Build the focused-slot dispatch job (if a technique is selected). Threads the
 * chosen single target onto the focused declaration (#1001a); the backend
 * resolves these PKs to instances scoped to the encounter.
 *
 * When a pull is selected, pull_resonance_id / pull_tier / pull_thread_ids are
 * merged into kwargs so the backend commits a CombatPull alongside the action.
 *
 * When a cast-time position is selected (#2206), `position_params` is merged
 * into kwargs: `{ destination_position_id }` for a "single"-shape technique,
 * or `{ position_a_id, position_b_id }` for a "pair"-shape technique.
 * Shape-aware per the selected action's `position_target_shape` — a
 * "none"/undefined-shape technique never gets `position_params`, even if
 * stale castPosition state is present (#2206 review finding).
 *
 * `isWardBearing` (#3573) - true when the selected technique carries a
 * protective ward (`reactive_anima_cost != null`). `confirm_soulfray_risk` is
 * sent when `soulfrayAccepted` is true AND either a Soulfray warning is active
 * OR the cast is ward-bearing - the lighter ward-cast toggle (rendered when no
 * warning is present) reuses the same `soulfrayAccepted` state as the
 * SoulfrayAcceptGate.
 */
function buildFocusedJob(
  focusedContext: ActionContext,
  effortLevel: string,
  dispatchAction: DispatchFn,
  selectedPull: PullSelection | null,
  soulfrayAccepted: boolean,
  soulfrayWarning: SoulfrayWarningData | null,
  furyTierId: number | null,
  furyAnchorId: number | null,
  castPosition: CastPosition,
  positionTargetShape: PositionTargetShape,
  isWardBearing: boolean
): DispatchJob | null {
  if (focusedContext.techniqueId === undefined) return null;

  const targetKwargs: Record<string, number> = {};
  if (focusedContext.targetId !== undefined) {
    if (focusedContext.targetKind === 'opponent') {
      targetKwargs.focused_opponent_target_id = focusedContext.targetId;
    } else if (focusedContext.targetKind === 'ally') {
      targetKwargs.focused_ally_target_id = focusedContext.targetId;
    }
  }

  const pullKwargs: Record<string, number | number[]> = {};
  if (selectedPull !== null) {
    pullKwargs.pull_resonance_id = selectedPull.resonance_id;
    pullKwargs.pull_tier = selectedPull.tier;
    pullKwargs.pull_thread_ids = selectedPull.thread_ids;
  }

  const furyKwargs: Record<string, number> = {};
  if (furyTierId !== null) furyKwargs.fury_commitment_id = furyTierId;
  if (furyAnchorId !== null) furyKwargs.fury_anchor_id = furyAnchorId;
  const soulfrayKwarg =
    soulfrayAccepted && (soulfrayWarning !== null || isWardBearing)
      ? { confirm_soulfray_risk: true }
      : {};

  // Strain (#3446): the push-yourself anima overcommit on an ordinary declared
  // cast — the non-clash sibling of the per-clash strain slider below.
  const strainKwarg =
    focusedContext.strainCommitment > 0
      ? { strain_commitment: focusedContext.strainCommitment }
      : {};

  // Strictly per-shape — never derive position_params from mere presence of
  // castPosition fields, since stale state from a previously-selected
  // technique can otherwise leak into a differently-shaped technique's
  // dispatch (#2206 review finding).
  type PositionParams =
    | { destination_position_id: number }
    | { position_a_id: number; position_b_id: number };
  const positionKwargs: Record<string, PositionParams> = {};
  if (positionTargetShape === 'single' && castPosition?.destinationId !== undefined) {
    positionKwargs.position_params = { destination_position_id: castPosition.destinationId };
  } else if (
    positionTargetShape === 'pair' &&
    castPosition?.pairA !== undefined &&
    castPosition?.pairB !== undefined
  ) {
    positionKwargs.position_params = {
      position_a_id: castPosition.pairA,
      position_b_id: castPosition.pairB,
    };
  }

  return () =>
    dispatchAction({
      ref: {
        backend: 'COMBAT',
        technique_id: focusedContext.techniqueId ?? null,
        action_slot: 'focused',
      },
      kwargs: {
        effort_level: effortLevel,
        ...targetKwargs,
        ...pullKwargs,
        ...soulfrayKwarg,
        ...strainKwarg,
        ...furyKwargs,
        ...positionKwargs,
      },
    });
}

/**
 * Build a dispatch job for each visible passive slot that has a technique.
 * Passives inherit the round effort declared on the focused slot.
 */
function buildPassiveJobs(
  visiblePassiveSlots: ActionSlot[],
  passiveContexts: Partial<Record<ActionSlot, ActionContext>>,
  effortLevel: string,
  dispatchAction: DispatchFn
): DispatchJob[] {
  const jobs: DispatchJob[] = [];
  for (const slot of visiblePassiveSlots) {
    const ctx = passiveContexts[slot];
    if (ctx != null && ctx.techniqueId !== undefined) {
      jobs.push(() =>
        dispatchAction({
          ref: {
            backend: 'COMBAT',
            technique_id: ctx.techniqueId ?? null,
            // `slot` is already the 'passive-<category>' string the backend's
            // CombatActionSlot expects — pass it straight through.
            action_slot: slot,
          },
          kwargs: { effort_level: effortLevel },
        })
      );
    }
  }
  return jobs;
}

/**
 * Build the clash-contribution dispatch job. technique_id goes in kwargs (NOT on
 * the ref) per plan Task 7.3: ActionRef.__post_init__ rejects both clash_id and
 * technique_id being set; see src/actions/types.py:137-155.
 *
 * When a pull is selected, pull_resonance_id / pull_tier / pull_thread_ids are
 * merged into kwargs so the backend commits a CombatPull alongside the clash.
 */
function buildClashJob(
  selectedClashRef: PlayerAction['ref'] | null,
  focusedContext: ActionContext,
  strainByClash: Record<number, number>,
  dispatchAction: DispatchFn,
  selectedPull: PullSelection | null
): DispatchJob | null {
  if (selectedClashRef === null || selectedClashRef.clash_id == null) return null;

  const clashId = selectedClashRef.clash_id;
  const strain = strainByClash[clashId] ?? 0;

  const pullKwargs: Record<string, number | number[]> = {};
  if (selectedPull !== null) {
    pullKwargs.pull_resonance_id = selectedPull.resonance_id;
    pullKwargs.pull_tier = selectedPull.tier;
    pullKwargs.pull_thread_ids = selectedPull.thread_ids;
  }

  return () =>
    dispatchAction({
      ref: {
        backend: 'COMBAT',
        clash_id: clashId,
        clash_action_slot: selectedClashRef.clash_action_slot ?? null,
      },
      kwargs: {
        // technique_id belongs here for clash contributions, not on the ref.
        technique_id: focusedContext.techniqueId,
        strain_commitment: strain,
        ...pullKwargs,
      },
    });
}

// ---------------------------------------------------------------------------
// ComboRow — renders one available combo as a button
// ---------------------------------------------------------------------------

interface ComboRowProps {
  combo: AvailableCombo;
  onUpgrade: (comboId: number) => void;
  isLoading: boolean;
}

function ComboRow({ combo, onUpgrade, isLoading }: ComboRowProps) {
  const isDisabled = !combo.known_by_participant || isLoading;
  const title = !combo.known_by_participant ? 'Combo not known' : undefined;

  return (
    <button
      type="button"
      disabled={isDisabled}
      title={title}
      onClick={() => onUpgrade(combo.combo_id)}
      data-testid={`combo-upgrade-btn-${combo.combo_id}`}
      className={cn(
        'w-full rounded border px-3 py-1.5 text-left text-xs font-medium transition-colors',
        'disabled:cursor-not-allowed disabled:opacity-50',
        isDisabled
          ? 'border-border bg-muted text-muted-foreground'
          : 'border-primary/40 bg-primary/5 text-primary hover:bg-primary/10'
      )}
    >
      Upgrade to {combo.combo_name} ({combo.slot_count} slots)
    </button>
  );
}

// ---------------------------------------------------------------------------
// ClashContributionRow — renders one clash PlayerAction as a commit button
// ---------------------------------------------------------------------------

interface ClashContributionRowProps {
  action: PlayerAction;
  strainCommitment: number;
  onSelectClash: (ref: PlayerAction['ref']) => void;
  onStrainChange: (value: number) => void;
  isSelected: boolean;
  /** Strain slider max — reads ParticipantSerializer.available_strain. Fallback 10. */
  strainMax?: number;
}

function ClashContributionRow({
  action,
  strainCommitment,
  onSelectClash,
  onStrainChange,
  isSelected,
  strainMax = 10,
}: ClashContributionRowProps) {
  return (
    <div
      className="space-y-2 rounded border border-border bg-card/60 p-2"
      data-testid={`clash-contribution-row-${action.ref.clash_id ?? 'unknown'}`}
    >
      <button
        type="button"
        onClick={() => onSelectClash(action.ref)}
        className={cn(
          'w-full rounded px-2 py-1 text-left text-xs font-medium transition-colors',
          isSelected
            ? 'border border-primary bg-primary/10 text-primary'
            : 'border border-border bg-background text-foreground hover:border-primary/50'
        )}
        data-testid={`clash-commit-btn-${action.ref.clash_id ?? 'unknown'}`}
      >
        Commit to clash {action.display_name}
      </button>

      {/* Strain slider — only shown when this clash is selected */}
      {isSelected && (
        <div className="space-y-1">
          <div className="flex items-center justify-between">
            <span className="text-[10px] uppercase tracking-wide text-muted-foreground">
              Strain commitment
            </span>
            <span className="font-mono text-xs text-foreground">{strainCommitment}</span>
          </div>
          <input
            type="range"
            min={0}
            max={strainMax}
            value={strainCommitment}
            onChange={(e) => onStrainChange(Number(e.target.value))}
            data-testid={`clash-strain-slider-${action.ref.clash_id ?? 'unknown'}`}
            className="w-full accent-primary"
            aria-label="Strain commitment"
          />
        </div>
      )}
    </div>
  );
}

/**
 * Resolve the ally name attached to a declared maneuver (cover/interpose), or
 * null when a different maneuver is declared or no ally target is set (a null
 * focused_ally_target on interpose means "guard whoever is hit", #2207).
 */
function maneuverAllyName(
  expectedManeuver: string,
  declaredManeuver: string | null,
  ownRoundAction: RoundActionTyped | null,
  participants: Participant[]
): string | null {
  if (declaredManeuver !== expectedManeuver || ownRoundAction?.focused_ally_target == null) {
    return null;
  }
  const ally = participants.find((p) => p.id === ownRoundAction.focused_ally_target);
  return ally?.character_name ?? `participant #${ownRoundAction.focused_ally_target}`;
}

/**
 * The reason the submit button must refuse, or null when clear to dispatch —
 * mirrors the required-declaration gating (#1543/#2206).
 */
function submitBlockReason(args: {
  soulfrayWarning: SoulfrayWarningData | null;
  soulfrayAccepted: boolean;
  furyOverCap: boolean;
  positionRequirementMet: boolean;
}): string | null {
  if (args.soulfrayWarning !== null && !args.soulfrayAccepted) {
    return 'Accept the Soulfray risk to proceed.';
  }
  if (args.furyOverCap) {
    return 'Chosen fury tier exceeds your bond with the anchor.';
  }
  if (!args.positionRequirementMet) {
    return 'Select a position target for this technique.';
  }
  return null;
}

type Opponent = NonNullable<EncounterDetail['opponents']>[number];
type InventoryItem = NonNullable<ReturnType<typeof useInventory>['data']>[number];

interface UseItemSectionProps {
  usableItems: InventoryItem[];
  coverableAllies: Participant[];
  activeOpponents: Opponent[];
  instanceId: string;
  targetValue: string;
  error: string | null;
  /** Every control is inert: locked, out of the declaring phase, or mid-dispatch. */
  disabled: boolean;
  /** Locked or out of phase, ignoring dispatch — drives the confirm button's styling. */
  inactive: boolean;
  pending: boolean;
  onInstanceChange: (value: string) => void;
  onTargetChange: (value: string) => void;
  onConfirm: () => void;
}

/**
 * Declare a held on-use item as this round's action (#3381, #2023/#2120).
 *
 * A primary maneuver, mutually exclusive with the focused technique slot.
 */
function UseItemSection({
  usableItems,
  coverableAllies,
  activeOpponents,
  instanceId,
  targetValue,
  error,
  disabled,
  inactive,
  pending,
  onInstanceChange,
  onTargetChange,
  onConfirm,
}: UseItemSectionProps) {
  if (usableItems.length === 0) return null;
  return (
    <div
      className="space-y-1.5 rounded border border-border bg-card/60 p-2"
      data-testid="use-item-section"
    >
      <p
        className="text-xs font-semibold uppercase tracking-wide text-muted-foreground"
        title="Use a held item as your round action, optionally against an ally or opponent."
      >
        Use Item
      </p>
      <Select value={instanceId} onValueChange={onInstanceChange} disabled={disabled}>
        <SelectTrigger data-testid="use-item-select" className="h-8 text-xs">
          <SelectValue placeholder="Choose an item…" />
        </SelectTrigger>
        <SelectContent>
          {usableItems.map((item) => (
            <SelectItem key={item.id} value={String(item.id)}>
              {item.display_name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <Select value={targetValue} onValueChange={onTargetChange} disabled={disabled}>
        <SelectTrigger data-testid="use-item-target-select" className="h-8 text-xs">
          <SelectValue placeholder="Target" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={USE_ITEM_TARGET_SELF}>Self / no target</SelectItem>
          {coverableAllies.map((ally) => (
            <SelectItem
              key={`use-item-ally-${ally.id}`}
              value={`${USE_ITEM_TARGET_ALLY_PREFIX}${ally.id}`}
            >
              {ally.character_name}
            </SelectItem>
          ))}
          {activeOpponents.map((opponent) => (
            <SelectItem
              key={`use-item-opponent-${opponent.id}`}
              value={`${USE_ITEM_TARGET_OPPONENT_PREFIX}${opponent.id}`}
            >
              {opponent.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <button
        type="button"
        disabled={disabled || instanceId === ''}
        onClick={onConfirm}
        data-testid="use-item-confirm-btn"
        className={cn(
          'w-full rounded-md border px-4 py-1.5 text-xs font-semibold transition-colors',
          'disabled:cursor-not-allowed disabled:opacity-50',
          inactive || instanceId === ''
            ? 'border-border bg-muted text-muted-foreground'
            : 'border-primary/40 bg-primary/5 text-primary hover:bg-primary/10'
        )}
      >
        {pending ? 'Using item…' : 'Use Item'}
      </button>
      {error !== null && (
        <p role="alert" className="text-sm text-destructive" data-testid="use-item-error">
          {error}
        </p>
      )}
    </div>
  );
}

interface MountedManeuversProps {
  activeOpponents: Opponent[];
  physicalTechniques: PlayerAction[];
  chargeOpponentId: string;
  chargeTechniqueId: string;
  chargeError: string | null;
  joustTechniqueId: string;
  joustError: string | null;
  /** Joust is offered only in a duel. */
  isDuelEncounter: boolean;
  /** Every control is inert: locked, out of the declaring phase, or mid-dispatch. */
  disabled: boolean;
  /** Locked or out of phase, ignoring dispatch — drives the buttons' styling. */
  inactive: boolean;
  pending: boolean;
  onChargeOpponentChange: (value: string) => void;
  onChargeTechniqueChange: (value: string) => void;
  onJoustTechniqueChange: (value: string) => void;
  onCharge: () => void;
  onJoust: () => void;
}

/**
 * Mounted-only declarations: close distance with a Charge, or Joust a duel
 * opponent (#3381, #1843).
 *
 * Backend-trusting per Decision 4: no client-side reach or Lance re-validation.
 * A rejected declaration surfaces the backend's own message inline.
 */
function MountedManeuvers({
  activeOpponents,
  physicalTechniques,
  chargeOpponentId,
  chargeTechniqueId,
  chargeError,
  joustTechniqueId,
  joustError,
  isDuelEncounter,
  disabled,
  inactive,
  pending,
  onChargeOpponentChange,
  onChargeTechniqueChange,
  onJoustTechniqueChange,
  onCharge,
  onJoust,
}: MountedManeuversProps) {
  return (
    <div
      className="space-y-2 rounded border border-border bg-card/60 p-2"
      data-testid="mounted-maneuvers-section"
    >
      <p
        className="text-xs font-semibold uppercase tracking-wide text-muted-foreground"
        title="Mounted-only declarations — close distance with a Charge, or Joust your duel opponent."
      >
        Mounted Maneuvers
      </p>

      {/* Charge — close distance to an opponent, then attack with the chosen technique. */}
      <div className="space-y-1.5" data-testid="charge-control">
        <Select value={chargeOpponentId} onValueChange={onChargeOpponentChange} disabled={disabled}>
          <SelectTrigger data-testid="charge-opponent-select" className="h-8 text-xs">
            <SelectValue placeholder="Charge which opponent…" />
          </SelectTrigger>
          <SelectContent>
            {activeOpponents.map((opponent) => (
              <SelectItem key={opponent.id} value={String(opponent.id)}>
                {opponent.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select
          value={chargeTechniqueId}
          onValueChange={onChargeTechniqueChange}
          disabled={disabled}
        >
          <SelectTrigger data-testid="charge-technique-select" className="h-8 text-xs">
            <SelectValue placeholder="With which technique…" />
          </SelectTrigger>
          <SelectContent>
            {physicalTechniques.map((action) => (
              <SelectItem
                key={action.ref.technique_id ?? action.display_name}
                value={String(action.ref.technique_id)}
              >
                {action.display_name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <button
          type="button"
          disabled={disabled || chargeOpponentId === '' || chargeTechniqueId === ''}
          onClick={onCharge}
          data-testid="charge-confirm-btn"
          className={cn(
            'w-full rounded-md border px-4 py-1.5 text-xs font-semibold transition-colors',
            'disabled:cursor-not-allowed disabled:opacity-50',
            inactive || chargeOpponentId === '' || chargeTechniqueId === ''
              ? 'border-border bg-muted text-muted-foreground'
              : 'border-orange-500/60 bg-orange-500/10 text-orange-300 hover:bg-orange-500/20'
          )}
        >
          {pending ? 'Charging…' : 'Charge'}
        </button>
        {chargeError !== null && (
          <p role="alert" className="text-sm text-destructive" data-testid="charge-error">
            {chargeError}
          </p>
        )}
      </div>

      {/* Joust — duel-only, opponent implied by the 2-participant duel. */}
      {isDuelEncounter && (
        <div className="space-y-1.5" data-testid="joust-control">
          <Select
            value={joustTechniqueId}
            onValueChange={onJoustTechniqueChange}
            disabled={disabled}
          >
            <SelectTrigger data-testid="joust-technique-select" className="h-8 text-xs">
              <SelectValue placeholder="Joust with which technique…" />
            </SelectTrigger>
            <SelectContent>
              {physicalTechniques.map((action) => (
                <SelectItem
                  key={action.ref.technique_id ?? action.display_name}
                  value={String(action.ref.technique_id)}
                >
                  {action.display_name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <button
            type="button"
            disabled={disabled || joustTechniqueId === ''}
            onClick={onJoust}
            data-testid="joust-confirm-btn"
            className={cn(
              'w-full rounded-md border px-4 py-1.5 text-xs font-semibold transition-colors',
              'disabled:cursor-not-allowed disabled:opacity-50',
              inactive || joustTechniqueId === ''
                ? 'border-border bg-muted text-muted-foreground'
                : 'border-orange-500/60 bg-orange-500/10 text-orange-300 hover:bg-orange-500/20'
            )}
          >
            {pending ? 'Jousting…' : 'Joust'}
          </button>
          {joustError !== null && (
            <p role="alert" className="text-sm text-destructive" data-testid="joust-error">
              {joustError}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

/** What this round's already-declared maneuver is, when there is one. */
function DeclaredManeuverBadge({
  declaredManeuver,
  coveredAllyName,
  guardedAllyName,
}: {
  declaredManeuver: string | null;
  coveredAllyName: string | null | undefined;
  guardedAllyName: string | null | undefined;
}) {
  if (declaredManeuver === 'flee') {
    return (
      <div
        className="rounded border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-300"
        data-testid="flee-declared-badge"
      >
        Fleeing: resolves at end of round
      </div>
    );
  }
  if (declaredManeuver === 'cover') {
    return (
      <div
        className="rounded border border-sky-500/40 bg-sky-500/10 px-3 py-2 text-xs text-sky-300"
        data-testid="cover-declared-badge"
      >
        Covering {coveredAllyName ?? 'ally'}
      </div>
    );
  }
  if (declaredManeuver === 'interpose') {
    return (
      <div
        className="rounded border border-violet-500/40 bg-violet-500/10 px-3 py-2 text-xs text-violet-300"
        data-testid="guard-declared-badge"
      >
        Guarding {guardedAllyName ?? 'any ally hit this round'}
      </div>
    );
  }
  return null;
}

interface CoverControlProps {
  declaredManeuver: string | null;
  coverableAllies: Participant[];
  coverAllyId: string;
  coverPending: boolean;
  isLocked: boolean;
  isDeclaringPhase: boolean;
  setCoverAllyId: (value: string) => void;
  handleCover: () => void;
}

/** Cover an ally, taking hits aimed at them. Hidden once cover is declared. */
function CoverControl({
  declaredManeuver,
  coverableAllies,
  coverAllyId,
  coverPending,
  isLocked,
  isDeclaringPhase,
  setCoverAllyId,
  handleCover,
}: CoverControlProps) {
  if (declaredManeuver === 'cover') return null;
  return (
    <div className="space-y-1.5" data-testid="cover-control">
      <Select
        value={coverAllyId}
        onValueChange={setCoverAllyId}
        disabled={isLocked || !isDeclaringPhase || coverPending}
      >
        <SelectTrigger data-testid="cover-ally-select" className="h-8 text-xs">
          <SelectValue placeholder="Cover an ally…" />
        </SelectTrigger>
        <SelectContent>
          {coverableAllies.map((ally) => (
            <SelectItem key={ally.id} value={String(ally.id)}>
              {ally.character_name}
            </SelectItem>
          ))}
          {coverableAllies.length === 0 && (
            <SelectItem value="__none__" disabled>
              No allies available
            </SelectItem>
          )}
        </SelectContent>
      </Select>
      <button
        type="button"
        disabled={isLocked || !isDeclaringPhase || coverPending || coverAllyId === ''}
        onClick={handleCover}
        data-testid="cover-confirm-btn"
        className={cn(
          'w-full rounded-md border px-4 py-1.5 text-xs font-semibold transition-colors',
          'disabled:cursor-not-allowed disabled:opacity-50',
          isLocked || !isDeclaringPhase || coverAllyId === ''
            ? 'border-border bg-muted text-muted-foreground'
            : 'border-sky-500/60 bg-sky-500/10 text-sky-300 hover:bg-sky-500/20'
        )}
      >
        {coverPending ? 'Declaring cover…' : 'Confirm Cover'}
      </button>
    </div>
  );
}

interface GuardControlProps {
  declaredManeuver: string | null;
  encounter: EncounterDetail | null | undefined;
  guardControlRef: React.RefObject<HTMLDivElement>;
  coverableAllies: Participant[];
  protectiveTechniques: PlayerAction[];
  selectedGuardTechnique: PlayerAction | undefined;
  isRedirectGuardTechnique: boolean;
  guardAllyId: string;
  guardTechniqueId: string;
  guardDestination: string;
  guardSoulfrayAccepted: boolean;
  animaCurrent: number | null;
  guardPending: boolean;
  isLocked: boolean;
  isDeclaringPhase: boolean;
  setGuardAllyId: (value: string) => void;
  setGuardTechniqueId: (value: string) => void;
  setGuardDestination: (value: string) => void;
  setGuardSoulfrayAccepted: (value: boolean) => void;
  handleGuard: () => void;
}

/**
 * Guard an ally with your body or a protective technique (#2207).
 *
 * Hidden once a guard is already declared this round; the declared state shows
 * in the cluster's badge instead.
 */
function GuardControl({
  declaredManeuver,
  encounter,
  guardControlRef,
  coverableAllies,
  protectiveTechniques,
  selectedGuardTechnique,
  isRedirectGuardTechnique,
  guardAllyId,
  guardTechniqueId,
  guardDestination,
  guardSoulfrayAccepted,
  animaCurrent,
  guardPending,
  isLocked,
  isDeclaringPhase,
  setGuardAllyId,
  setGuardTechniqueId,
  setGuardDestination,
  setGuardSoulfrayAccepted,
  handleGuard,
}: GuardControlProps) {
  if (declaredManeuver === 'interpose') return null;
  return (
    <div className="space-y-1.5" data-testid="guard-control" ref={guardControlRef}>
      <Select
        value={guardAllyId}
        onValueChange={setGuardAllyId}
        disabled={isLocked || !isDeclaringPhase || guardPending}
      >
        <SelectTrigger data-testid="guard-ally-select" className="h-8 text-xs">
          <SelectValue placeholder="Guard anyone…" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={GUARD_ANYONE_VALUE}>Anyone (guard whoever is hit)</SelectItem>
          {coverableAllies.map((ally) => (
            <SelectItem key={ally.id} value={String(ally.id)}>
              {ally.character_name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      {protectiveTechniques.length > 0 && (
        <Select
          value={guardTechniqueId}
          onValueChange={(value) => {
            setGuardTechniqueId(value);
            // Switching back to mundane clears any prior Soulfray
            // consent - there's no protective ward left to hold (#3573).
            if (value === GUARD_NO_TECHNIQUE_VALUE) setGuardSoulfrayAccepted(false);
          }}
          disabled={isLocked || !isDeclaringPhase || guardPending}
        >
          <SelectTrigger data-testid="guard-technique-select" className="h-8 text-xs">
            <SelectValue placeholder="No protective technique" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={GUARD_NO_TECHNIQUE_VALUE}>
              No protective technique (mundane)
            </SelectItem>
            {protectiveTechniques.map((action) => (
              <SelectItem
                key={action.ref.technique_id ?? action.display_name}
                value={String(action.ref.technique_id)}
              >
                {action.display_name}
                {action.protective_flavor != null
                  ? ` (${PROTECTIVE_FLAVOR_LABELS[action.protective_flavor] ?? action.protective_flavor})`
                  : ''}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      )}

      {selectedGuardTechnique != null && (
        <label
          className="flex items-center gap-2 rounded-md border border-amber-500/60 bg-amber-950/40 px-2 py-1.5 text-xs"
          data-testid="guard-soulfray-gate"
        >
          <input
            type="checkbox"
            data-testid="guard-soulfray-toggle"
            checked={guardSoulfrayAccepted}
            onChange={(e) => setGuardSoulfrayAccepted(e.target.checked)}
            disabled={isLocked || !isDeclaringPhase || guardPending}
          />
          <span>
            Hold the line into Soulfray
            {animaCurrent != null && selectedGuardTechnique.reactive_anima_cost != null
              ? ` (anima ${animaCurrent} / fee ${selectedGuardTechnique.reactive_anima_cost})`
              : ''}
          </span>
        </label>
      )}

      {isRedirectGuardTechnique && (
        <Select
          value={guardDestination}
          onValueChange={setGuardDestination}
          disabled={isLocked || !isDeclaringPhase || guardPending}
        >
          <SelectTrigger data-testid="guard-redirect-destination-select" className="h-8 text-xs">
            <SelectValue placeholder="Redirect destination" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={GUARD_DESTINATION_AWAY}>Away (default)</SelectItem>
            {(encounter?.opponents ?? []).map((opponent) => (
              <SelectItem
                key={`opp-${opponent.id}`}
                value={`${GUARD_DESTINATION_OPPONENT_PREFIX}${opponent.id}`}
              >
                {opponent.name}
              </SelectItem>
            ))}
            {(encounter?.volatile_objects ?? []).map((volatileObject) => (
              <SelectItem
                key={`obj-${volatileObject.id}`}
                value={`${GUARD_DESTINATION_OBJECT_PREFIX}${volatileObject.id}`}
              >
                {volatileObject.name}
                {volatileObject.position_name != null ? ` (${volatileObject.position_name})` : ''}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      )}

      <button
        type="button"
        disabled={isLocked || !isDeclaringPhase || guardPending}
        onClick={handleGuard}
        data-testid="guard-confirm-btn"
        className={cn(
          'w-full rounded-md border px-4 py-1.5 text-xs font-semibold transition-colors',
          'disabled:cursor-not-allowed disabled:opacity-50',
          isLocked || !isDeclaringPhase
            ? 'border-border bg-muted text-muted-foreground'
            : 'border-violet-500/60 bg-violet-500/10 text-violet-300 hover:bg-violet-500/20'
        )}
      >
        {guardPending ? 'Declaring guard…' : 'Guard'}
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// YourTurn
// ---------------------------------------------------------------------------

export function YourTurn({
  encounterId,
  characterId,
  characterSheetId,
  roundNumber,
  availableActions,
  readOnly = false,
  availableStrain,
  encounter = null,
  castPosition: castPositionProp,
  onCastPositionChange: onCastPositionChangeProp,
  onPositionShapeChange,
}: YourTurnProps) {
  const strainMax = availableStrain ?? 10;
  const queryClient = useQueryClient();
  // ---------------------------------------------------------------------------
  // Round-scoped state (#2423 finding 4) — consolidated into one object,
  // reset WHOLESALE on round advance (see initialRoundState above).
  // ---------------------------------------------------------------------------

  const [roundState, setRoundState] = useState<RoundScopedState>(initialRoundState);
  const {
    focusedContext,
    passiveContexts,
    selectedClashRef,
    strainByClash,
    submitted,
    submitError,
    pullDialogOpen,
    selectedPull,
    soulfrayAccepted,
    furyTierId,
    furyAnchorId,
    coverAllyId,
    maneuverError,
    guardAllyId,
    guardTechniqueId,
    guardDestination,
    guardSoulfrayAccepted,
    rallyAllyId,
    succorAllyId,
    useItemInstanceId,
    useItemTargetValue,
    useItemError,
    chargeOpponentId,
    chargeTechniqueId,
    chargeError,
    joustTechniqueId,
    joustError,
  } = roundState;

  // Per-field setter preserving React.SetStateAction semantics so every
  // existing call site (~60 across this file and child-component props)
  // compiles unchanged. Defined inside the component (not module level) so it
  // closes over `setRoundState`; `setRoundState` from `useState` is stable, so
  // the `useMemo([])` deps below are correct. `makeFieldSetter` itself is a
  // fresh function object every render, but that's harmless: it's a pure
  // factory (no closure over per-render values besides the stable
  // `setRoundState`) and nothing holds a reference to it by identity across
  // renders — only the memoized setters it returns are read, and those never
  // need to change.
  function makeFieldSetter<K extends keyof RoundScopedState>(key: K) {
    return (value: SetStateAction<RoundScopedState[K]>) => {
      setRoundState((prev) => ({
        ...prev,
        [key]:
          typeof value === 'function'
            ? (value as (p: RoundScopedState[K]) => RoundScopedState[K])(prev[key])
            : value,
      }));
    };
  }
  const setFocusedContext = useMemo(() => makeFieldSetter('focusedContext'), []);
  const setPassiveContexts = useMemo(() => makeFieldSetter('passiveContexts'), []);
  const setSelectedClashRef = useMemo(() => makeFieldSetter('selectedClashRef'), []);
  const setStrainByClash = useMemo(() => makeFieldSetter('strainByClash'), []);
  const setSubmitted = useMemo(() => makeFieldSetter('submitted'), []);
  const setSubmitError = useMemo(() => makeFieldSetter('submitError'), []);
  const setPullDialogOpen = useMemo(() => makeFieldSetter('pullDialogOpen'), []);
  const setSelectedPull = useMemo(() => makeFieldSetter('selectedPull'), []);
  const setSoulfrayAccepted = useMemo(() => makeFieldSetter('soulfrayAccepted'), []);
  const setFuryTierId = useMemo(() => makeFieldSetter('furyTierId'), []);
  const setFuryAnchorId = useMemo(() => makeFieldSetter('furyAnchorId'), []);
  const setCoverAllyId = useMemo(() => makeFieldSetter('coverAllyId'), []);
  const setManeuverError = useMemo(() => makeFieldSetter('maneuverError'), []);
  const setGuardAllyId = useMemo(() => makeFieldSetter('guardAllyId'), []);
  const setGuardTechniqueId = useMemo(() => makeFieldSetter('guardTechniqueId'), []);
  const setGuardDestination = useMemo(() => makeFieldSetter('guardDestination'), []);
  const setGuardSoulfrayAccepted = useMemo(() => makeFieldSetter('guardSoulfrayAccepted'), []);
  const setRallyAllyId = useMemo(() => makeFieldSetter('rallyAllyId'), []);
  const setSuccorAllyId = useMemo(() => makeFieldSetter('succorAllyId'), []);
  const setUseItemInstanceId = useMemo(() => makeFieldSetter('useItemInstanceId'), []);
  const setUseItemTargetValue = useMemo(() => makeFieldSetter('useItemTargetValue'), []);
  const setUseItemError = useMemo(() => makeFieldSetter('useItemError'), []);
  const setChargeOpponentId = useMemo(() => makeFieldSetter('chargeOpponentId'), []);
  const setChargeTechniqueId = useMemo(() => makeFieldSetter('chargeTechniqueId'), []);
  const setChargeError = useMemo(() => makeFieldSetter('chargeError'), []);
  const setJoustTechniqueId = useMemo(() => makeFieldSetter('joustTechniqueId'), []);
  const setJoustError = useMemo(() => makeFieldSetter('joustError'), []);

  // Cast-time position selection for the focused technique (#2206). Controlled
  // by the caller when castPositionProp/onCastPositionChangeProp are supplied
  // (CombatRail lifts this above the rail tabs so the tactical-map tab
  // shares it); falls back to local state otherwise (e.g. standalone tests).
  // NOT part of RoundScopedState — stays lifted/controlled exactly as before.
  const [localCastPosition, setLocalCastPosition] = useState<CastPosition>({});
  const castPosition = castPositionProp ?? localCastPosition;
  const setCastPosition = onCastPositionChangeProp ?? setLocalCastPosition;

  // Did-mount guards for the two reset effects below (#2206 review finding).
  // Both effects' dependencies take on their "changed" value on first mount
  // too (standard React) — without a guard, mounting/remounting this panel
  // (e.g. switching from the Map tab back to Your Turn, which unmounts and
  // remounts inactive TabsContent) would fire `setCastPosition({})` and wipe
  // out a position the caller already lifted into `castPosition`/
  // `onCastPositionChange`. Skip the reset on the mount that establishes each
  // ref; only fire on genuine post-mount transitions.
  const roundResetMounted = useRef(false);
  const techniqueResetMounted = useRef(false);

  // Reset every round-scoped atom WHOLESALE when round advances (#2423) — a
  // single `setRoundState(initialRoundState())` makes "forgot to reset one
  // field" bugs structurally impossible.
  useEffect(() => {
    if (!roundResetMounted.current) {
      roundResetMounted.current = true;
      return;
    }
    setRoundState(initialRoundState());
    setCastPosition({});
  }, [roundNumber, setCastPosition]);

  // Reset cast-time position selection when the focused technique changes —
  // a position picked for a prior technique (e.g. a pair-shape technique's A/B)
  // must not silently leak into a differently-shaped technique's
  // `position_params` (#2206 review finding).
  useEffect(() => {
    if (!techniqueResetMounted.current) {
      techniqueResetMounted.current = true;
      return;
    }
    setCastPosition({});
  }, [focusedContext.techniqueId, setCastPosition]);

  // ---------------------------------------------------------------------------
  // Slot composition
  // ---------------------------------------------------------------------------

  const focusedCategory = resolveFocusedCategory(focusedContext, availableActions);
  const visiblePassiveSlots = passiveSlotsToRender(focusedCategory);

  // ---------------------------------------------------------------------------
  // Clash actions from availableActions (COMBAT backend + clash_id set)
  // ---------------------------------------------------------------------------

  const clashActions = availableActions.filter(
    (a) => a.ref.backend === 'combat' && a.ref.clash_id != null
  );

  // ---------------------------------------------------------------------------
  // Move-to-position actions from availableActions (registry backend, #532)
  // ---------------------------------------------------------------------------

  const moveActions = availableActions.filter(
    (a) => a.ref.backend === 'registry' && a.ref.registry_key === 'move_to_position'
  );

  // ---------------------------------------------------------------------------
  // Combos
  // ---------------------------------------------------------------------------

  const { data: availableCombos, isLoading: combosLoading } = useAvailableCombos(encounterId);
  const { mutate: upgradeCombo, isPending: upgradePending } = useUpgradeCombo(encounterId);

  // ---------------------------------------------------------------------------
  // Flee / Cover mutations
  // ---------------------------------------------------------------------------

  const { mutate: declareFlee, isPending: fleePending } = useFleeMutation(encounterId);
  const { mutate: declareCover, isPending: coverPending } = useCoverMutation(encounterId);
  const { mutate: declareGuard, isPending: guardPending } = useGuardMutation(
    encounterId,
    characterId
  );

  // ---------------------------------------------------------------------------
  // Flee / Cover — derived state
  // ---------------------------------------------------------------------------

  // Gates flee/cover on the declaring phase.
  const isDeclaringPhase = encounter?.status === 'declaring';

  // Derive the viewer's participant PK from the participants list — stable
  // regardless of whether current_round_actions is ordered or GM-visible (all
  // actions). characterSheetId matches character_sheet_id on the Participant row.
  const myParticipantId: number | null = (() => {
    const ps = encounter?.participants ?? [];
    const self = ps.find((p) => p.character_sheet_id === characterSheetId);
    return self?.id ?? null;
  })();

  // Own round action — find by participant PK, not positional [0].
  const ownRoundAction: RoundActionTyped | null = (() => {
    if (myParticipantId === null) return null;
    const actions = encounter?.current_round_actions ?? [];
    const match = actions.find(
      (a) =>
        typeof (a as RoundActionTyped).participant === 'number' &&
        (a as RoundActionTyped).participant === myParticipantId
    );
    return (match as RoundActionTyped) ?? null;
  })();

  // Server-derived ready lock (#2423): CombatRail's Radix tabs unmount inactive
  // TabsContent, so switching to the Map tab and back remounts this component
  // and resets local `submitted` to false — even though the server already has
  // this participant's round action marked ready. Deriving the lock from
  // ownRoundAction.is_ready (not just local state) survives that remount.
  const serverReady = ownRoundAction?.is_ready === true;

  const participants: Participant[] = encounter?.participants ?? [];

  // All active participants except self count as allies until covenant sides land (mirrors backend serializers.py note).
  const coverableAllies = participants.filter(
    (p) => p.status === 'active' && p.id !== myParticipantId
  );

  // The viewer's own participant row — shared by actorPositionId below and the
  // Mounted-condition gate for the Charge/Joust mini-panel (#3381).
  const myParticipantSelf: Participant | null =
    myParticipantId === null
      ? null
      : ((encounter?.participants ?? []).find((p) => p.id === myParticipantId) ?? null);

  // Actor's position — the viewer's own participant's current_position.
  const actorPositionId: number | null = myParticipantSelf?.current_position?.id ?? null;

  // Mounted Maneuvers gate (#3381 Decision 4): visibility keyed off the cheap,
  // already-serialized `active_conditions` signal — no client-side
  // re-implementation of Mounted+Lance+reach validation, which the backend
  // already owns (ChargeAction/JoustAction's own prerequisite checks).
  const isMounted = ((myParticipantSelf?.active_conditions ?? []) as ConditionInstance[]).some(
    (c) => c.name === MOUNTED_CONDITION_NAME
  );
  const isDuelEncounter = encounter?.encounter_type === 'duel';

  // Active opponents — reused by the opponent-targeted Use Item picker and
  // Charge's opponent select (same source CombatantsList/focusedTargets read).
  const activeOpponents = (encounter?.opponents ?? []).filter((o) => o.status === 'active');

  // Focused-target options (#1001a): active opponents + allies. Opponents carry
  // their ObjectDB id for the applicable-pulls API; the dispatch uses the
  // CombatOpponent / CombatParticipant PK (`id`). Each option also carries
  // positionId for the reach pre-filter (#532).
  const focusedTargets: TargetOption[] = [
    ...(encounter?.opponents ?? [])
      .filter((o) => o.status === 'active')
      .map((o) => ({
        id: o.id,
        kind: 'opponent' as const,
        name: o.name,
        objectId: o.objectdb_id,
        positionId: o.current_position?.id ?? null,
      })),
    ...coverableAllies.map((p) => ({
      id: p.id,
      kind: 'ally' as const,
      name: p.character_name,
      positionId: p.current_position?.id ?? null,
    })),
  ];

  // The selected focused technique's action descriptor — one lookup shared by
  // the reach constraint (#532), the position-targeting shape (#2206), and the
  // soulfray/fury descriptor (#1543) below.
  const focusedCastDescriptor =
    focusedContext.techniqueId === undefined
      ? null
      : (availableActions.find((a) => a.ref.technique_id === focusedContext.techniqueId) ?? null);

  // Reach constraint for the currently selected focused technique (#532).
  const focusedTechniqueReach: string | null = focusedCastDescriptor?.reach ?? null;

  // Cast-time position-targeting shape for the currently selected focused
  // technique (#2206). Positions/edges data is the same source
  // CombatTacticalMap uses — EncounterDetail.position_nodes.
  const focusedTechniquePositionShape: PositionTargetShape =
    focusedCastDescriptor?.position_target_shape ?? 'none';
  const focusedPositions: PositionNode[] = encounter?.position_nodes ?? [];

  // Report the current shape to the caller (#2206) — lets the tactical-map tab
  // know whether map-click position-picking should be active, and keeps
  // knowing even after this panel unmounts on tab switch (CombatRail's
  // state persists across its children's mount/unmount).
  useEffect(() => {
    onPositionShapeChange?.(focusedTechniquePositionShape);
  }, [focusedTechniquePositionShape, onPositionShapeChange]);

  // Blocks Ready/submit while a required position slot is empty (#2206,
  // mirrors the fury/soulfray required-declaration gating below).
  const positionRequirementMet =
    focusedTechniquePositionShape === 'none' ||
    (focusedTechniquePositionShape === 'single' && castPosition.destinationId !== undefined) ||
    (focusedTechniquePositionShape === 'pair' &&
      castPosition.pairA !== undefined &&
      castPosition.pairB !== undefined);

  // Soulfray + fury descriptor for the currently selected focused cast (#1543).
  const soulfrayWarning = focusedCastDescriptor?.soulfray_warning ?? null;
  // Whether the selected focused technique carries a protective ward (#3573) -
  // consent must ALWAYS be offered for a ward-bearing cast, not just when an
  // active Soulfray warning is already in effect. When a warning IS present,
  // the SoulfrayAcceptGate below is the only control; its acceptance already
  // covers the ward (see the soulfrayKwarg logic in buildFocusedJob).
  const isWardBearingCast = focusedCastDescriptor?.reactive_anima_cost != null;
  const furyTiers = focusedCastDescriptor?.available_fury_tiers ?? [];
  const furyAnchors = focusedCastDescriptor?.eligible_fury_anchors ?? [];
  const furyOverCap =
    furyTierId !== null &&
    furyAnchorId !== null &&
    (furyTiers.find((t) => t.id === furyTierId)?.depth ?? 0) >
      (furyAnchors.find((a) => a.id === furyAnchorId)?.provocation_cap ?? 0);

  // Current declared maneuver (from own round action).
  const declaredManeuver = ownRoundAction?.maneuver ?? null;

  // Resolve covered ally's name from participants list.
  const coveredAllyName = maneuverAllyName('cover', declaredManeuver, ownRoundAction, participants);

  // Resolve guarded ally's name from participants list (#2207). null
  // focused_ally_target on an interpose maneuver means "guard whoever is hit."
  const guardedAllyName = maneuverAllyName(
    'interpose',
    declaredManeuver,
    ownRoundAction,
    participants
  );

  // Techniques offered as a Guard's optional protective technique (#2207): any
  // available combat-cast technique whose protective_flavor classifier resolved.
  // 'redirect' techniques resolve since #2210 — the destination picker below
  // surfaces when one is selected.
  const protectiveTechniques = availableActions.filter(
    (a) => a.ref.backend === 'combat' && a.protective_flavor != null && a.ref.technique_id != null
  );

  // The currently-selected guard technique's protective flavor (#2210) — gates
  // the redirect destination picker.
  const selectedGuardTechnique = protectiveTechniques.find(
    (a) => String(a.ref.technique_id) === guardTechniqueId
  );
  const isRedirectGuardTechnique = selectedGuardTechnique?.protective_flavor === 'redirect';

  // Current anima, shown next to the Guard Soulfray toggle's fee readout
  // (#3573) and the ward-cast toggle below, so the guardian/caster can see
  // what they're spending before consenting.
  const { data: characterAnima } = useCharacterAnima(characterId);
  const animaCurrent = characterAnima?.current ?? null;

  // Usable held items for the Use Item control (#3381) — filters the same
  // inventory query the wardrobe/inventory panel uses, no new endpoint.
  const { data: inventoryItems = [] } = useInventory(characterId > 0 ? characterId : undefined);
  const usableItems = inventoryItems.filter((item) => item.is_usable);

  // Physical-category combat techniques, offered by Charge/Joust's technique
  // picker (#3381) — a minimal `<select>`, not the full ActionDeclarationCard
  // (Decision 4: no client-side reach/prerequisite duplication).
  const physicalTechniques = availableActions.filter(
    (a) =>
      a.ref.backend === 'combat' && a.ref.technique_id != null && a.action_category === 'physical'
  );

  // ---------------------------------------------------------------------------
  // Dispatch
  // ---------------------------------------------------------------------------

  const { mutateAsync: dispatchAction, isPending: dispatchPending } =
    useDispatchPlayerAction(characterId);

  // #3381 — shared registry-dispatch mutation for the new maneuvers below
  // (rally/succor/use-item/revert/charge/joust). One mutation instance is
  // fine to share across all of them: none of these controls can be
  // in-flight simultaneously (a single participant declares one round action).
  const { mutateAsync: dispatchManeuver, isPending: maneuverDispatchPending } = useRegistryDispatch(
    encounterId,
    characterId
  );

  // ---------------------------------------------------------------------------
  // Submit handler
  // ---------------------------------------------------------------------------

  async function handleSubmit() {
    if (submitted || serverReady || dispatchPending) return;

    setSubmitError(null);

    const blockReason = submitBlockReason({
      soulfrayWarning,
      soulfrayAccepted,
      furyOverCap,
      positionRequirementMet,
    });
    if (blockReason !== null) {
      setSubmitError(blockReason);
      return;
    }

    // The round effort comes from the focused slot and applies to every
    // declaration (focused + passives). The COMBAT dispatch requires
    // effort_level in kwargs on every ref or it rejects (UNKNOWN_ACTION_REF).
    const effortLevel = EFFORT_TO_BACKEND[focusedContext.effort];

    // Submission order per plan: focused first, then passives, then clashes
    // (focused first guarantees the server sees focused before passives).
    // selectedPull (if any) rides on focused and clash kwargs — the backend
    // commits a CombatPull when those kwargs are present.
    const focusedJob = buildFocusedJob(
      focusedContext,
      effortLevel,
      dispatchAction,
      selectedPull,
      soulfrayAccepted,
      soulfrayWarning,
      furyTierId,
      furyAnchorId,
      castPosition,
      focusedTechniquePositionShape,
      isWardBearingCast
    );
    const passiveJobs = buildPassiveJobs(
      visiblePassiveSlots,
      passiveContexts,
      effortLevel,
      dispatchAction
    );
    const clashJob = buildClashJob(
      selectedClashRef,
      focusedContext,
      strainByClash,
      dispatchAction,
      selectedPull
    );

    const dispatchJobs: DispatchJob[] = [
      ...(focusedJob ? [focusedJob] : []),
      ...passiveJobs,
      ...(clashJob ? [clashJob] : []),
    ];

    try {
      for (const job of dispatchJobs) {
        const result = await job();
        // The dispatch endpoint always resolves 200 for a business-rule
        // rejection (only a structural ref error is a 400) — success:false
        // must be checked explicitly, or an honest-failure job would silently
        // flip the local `submitted`/ready state (#2423).
        if (isDispatchFailure(result)) {
          setSubmitError(result.message ?? 'Submit failed. Try again.');
          return;
        }
      }
      // PaceMode.READY early-resolution (#3067): `declare_action` resets
      // `is_ready=False` on every declaration, so submitting alone never
      // marks the participant ready — a READY-pace encounter would then
      // wait out the TIMED-style sweep instead of resolving the instant
      // everyone's in. Dispatch the same `combat_ready` registry action the
      // REST `ready` endpoint / telnet `combat ready` use, mirroring
      // `ReadyAction.execute` -> `maybe_resolve_on_ready`. Only meaningful in
      // READY pace — TIMED resolves on its timer and MANUAL waits for the GM,
      // so this is skipped for both to leave their behavior unchanged.
      if (encounter?.pace_mode === 'ready') {
        const readyResult = await dispatchAction({
          ref: { backend: 'registry', registry_key: 'combat_ready' },
          kwargs: {},
        });
        if (isDispatchFailure(readyResult)) {
          setSubmitError(readyResult.message ?? 'Submit failed. Try again.');
          return;
        }
      }
      setSubmitted(true);
      // Refresh the encounter (carries the server's is_ready) and the "Last
      // Outcome" panel now that every declared job succeeded (#2423).
      queryClient
        .invalidateQueries({ queryKey: combatKeys.encounter(encounterId) })
        .catch(() => {});
      invalidateConsequenceOutcomes(queryClient);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Submit failed. Try again.';
      setSubmitError(message);
    }
  }

  // ---------------------------------------------------------------------------
  // Flee / Cover handlers
  // ---------------------------------------------------------------------------

  function handleFlee() {
    setManeuverError(null);
    declareFlee(undefined, {
      onError: (err) => {
        setManeuverError(err instanceof Error ? err.message : 'Failed to declare flee');
      },
    });
  }

  function handleCover() {
    const allyId = parseInt(coverAllyId, 10);
    if (!allyId) {
      setManeuverError('Select an ally to cover');
      return;
    }
    setManeuverError(null);
    declareCover(allyId, {
      onError: (err) => {
        setManeuverError(err instanceof Error ? err.message : 'Failed to declare cover');
      },
    });
  }

  // Pending-attacks strip prefills (#3572) - Guard the wind-up's target, or
  // steer the focused declaration at the opponent still winding it up.
  const guardControlRef = useRef<HTMLDivElement | null>(null);
  function handlePrefillGuard(targetParticipantId: number) {
    setGuardAllyId(String(targetParticipantId));
    guardControlRef.current?.scrollIntoView({ block: 'nearest' });
  }
  function handlePrefillStrike(opponentId: number) {
    setSubmitError(null);
    setFocusedContext((prev) => ({ ...prev, targetKind: 'opponent', targetId: opponentId }));
  }

  function handleGuard() {
    setManeuverError(null);
    const allyParticipantId =
      guardAllyId === GUARD_ANYONE_VALUE ? null : parseInt(guardAllyId, 10) || null;
    const techniqueId =
      guardTechniqueId === GUARD_NO_TECHNIQUE_VALUE ? null : parseInt(guardTechniqueId, 10) || null;
    // Redirect destination (#2210) — "away" (the sentinel default) sends
    // neither kwarg, matching the backend's own null-means-away default.
    let redirectOpponentTargetId: number | null = null;
    let redirectObjectTargetId: number | null = null;
    if (guardDestination.startsWith(GUARD_DESTINATION_OPPONENT_PREFIX)) {
      redirectOpponentTargetId =
        parseInt(guardDestination.slice(GUARD_DESTINATION_OPPONENT_PREFIX.length), 10) || null;
    } else if (guardDestination.startsWith(GUARD_DESTINATION_OBJECT_PREFIX)) {
      redirectObjectTargetId =
        parseInt(guardDestination.slice(GUARD_DESTINATION_OBJECT_PREFIX.length), 10) || null;
    }
    declareGuard(
      {
        allyParticipantId,
        techniqueId,
        redirectOpponentTargetId,
        redirectObjectTargetId,
        confirmSoulfrayRisk: techniqueId != null && guardSoulfrayAccepted,
      },
      {
        onSuccess: (result) => {
          // The generic dispatch endpoint always resolves 200 — a business-rule
          // rejection (e.g. "not in active round") surfaces as success:false,
          // not a thrown error, so it must be checked explicitly here.
          if (result?.success === false) {
            setManeuverError(result.message ?? 'Failed to declare guard');
          }
        },
        onError: (err) => {
          setManeuverError(err instanceof Error ? err.message : 'Failed to declare guard');
        },
      }
    );
  }

  // ---------------------------------------------------------------------------
  // #3381 handlers — rally/succor/use-item/revert-combo/charge/joust. All ride
  // the shared dispatchManeuver mutation (useRegistryDispatch) declared above.
  // ---------------------------------------------------------------------------

  async function handleRally() {
    const allyId = parseInt(rallyAllyId, 10);
    if (!allyId) {
      setManeuverError('Select an ally to rally.');
      return;
    }
    setManeuverError(null);
    try {
      const result = await dispatchManeuver({
        registryKey: 'combat_rally',
        kwargs: { ally_participant_id: allyId },
      });
      if (isDispatchFailure(result)) {
        setManeuverError(result.message ?? 'Failed to declare rally.');
      }
    } catch (err) {
      setManeuverError(err instanceof Error ? err.message : 'Failed to declare rally.');
    }
  }

  async function handleSuccor() {
    const allyId = parseInt(succorAllyId, 10);
    if (!allyId) {
      setManeuverError('Select an ally to shelter.');
      return;
    }
    setManeuverError(null);
    try {
      const result = await dispatchManeuver({
        registryKey: 'combat_succor',
        kwargs: { ally_participant_id: allyId },
      });
      if (isDispatchFailure(result)) {
        setManeuverError(result.message ?? 'Failed to declare succor.');
      }
    } catch (err) {
      setManeuverError(err instanceof Error ? err.message : 'Failed to declare succor.');
    }
  }

  async function handleUseItem() {
    const itemInstanceId = parseInt(useItemInstanceId, 10);
    if (!itemInstanceId) {
      setUseItemError('Select an item to use.');
      return;
    }
    setUseItemError(null);
    // At most one of ally_participant_id / opponent_id (mirrors UseItemSerializer's
    // mutual-exclusivity, #2120) — "self" (the default) sends neither.
    const kwargs: Record<string, number> = { item_instance_id: itemInstanceId };
    if (useItemTargetValue.startsWith(USE_ITEM_TARGET_ALLY_PREFIX)) {
      const allyId = parseInt(useItemTargetValue.slice(USE_ITEM_TARGET_ALLY_PREFIX.length), 10);
      if (allyId) kwargs.ally_participant_id = allyId;
    } else if (useItemTargetValue.startsWith(USE_ITEM_TARGET_OPPONENT_PREFIX)) {
      const opponentId = parseInt(
        useItemTargetValue.slice(USE_ITEM_TARGET_OPPONENT_PREFIX.length),
        10
      );
      if (opponentId) kwargs.opponent_id = opponentId;
    }
    try {
      const result = await dispatchManeuver({ registryKey: 'combat_use', kwargs });
      if (isDispatchFailure(result)) {
        setUseItemError(result.message ?? 'Failed to use item.');
      }
    } catch (err) {
      setUseItemError(err instanceof Error ? err.message : 'Failed to use item.');
    }
  }

  async function handleRevertCombo() {
    setManeuverError(null);
    try {
      const result = await dispatchManeuver({ registryKey: 'combat_revert' });
      if (isDispatchFailure(result)) {
        setManeuverError(result.message ?? 'Failed to revert combo.');
      }
    } catch (err) {
      setManeuverError(err instanceof Error ? err.message : 'Failed to revert combo.');
    }
  }

  async function handleCharge() {
    const opponentId = parseInt(chargeOpponentId, 10);
    const techniqueId = parseInt(chargeTechniqueId, 10);
    if (!opponentId || !techniqueId) {
      setChargeError('Select an opponent and a technique to charge with.');
      return;
    }
    setChargeError(null);
    try {
      const result = await dispatchManeuver({
        registryKey: 'combat_charge',
        kwargs: { opponent_id: opponentId, technique_id: techniqueId },
      });
      if (isDispatchFailure(result)) {
        setChargeError(result.message ?? 'Failed to charge.');
      }
    } catch (err) {
      setChargeError(err instanceof Error ? err.message : 'Failed to charge.');
    }
  }

  async function handleJoust() {
    const techniqueId = parseInt(joustTechniqueId, 10);
    if (!techniqueId) {
      setJoustError('Select a technique to joust with.');
      return;
    }
    setJoustError(null);
    try {
      const result = await dispatchManeuver({
        registryKey: 'combat_joust',
        kwargs: { technique_id: techniqueId },
      });
      if (isDispatchFailure(result)) {
        setJoustError(result.message ?? 'Failed to joust.');
      }
    } catch (err) {
      setJoustError(err instanceof Error ? err.message : 'Failed to joust.');
    }
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  const isLocked = readOnly || submitted || serverReady;

  const renderDispatch = () => {
    if (dispatchPending) {
      return 'Submitting…';
    }
    if (encounter?.pace_mode === 'ready') {
      return 'Submit declarations · mark ready';
    }
    return 'Submit declarations';
  };

  return (
    <div className="space-y-4" data-testid="your-turn-section">
      <PendingAttacks
        attacks={encounter?.pending_attacks ?? []}
        viewerParticipantId={myParticipantId}
        onGuard={readOnly ? undefined : handlePrefillGuard}
        onStrike={readOnly ? undefined : handlePrefillStrike}
      />

      {/* Submitted / ready badge */}
      {(submitted || serverReady) && (
        <div
          className="rounded-md border border-emerald-500/40 bg-emerald-500/10 px-3 py-2 text-center text-sm font-medium text-emerald-300"
          data-testid="ready-badge"
        >
          Ready: waiting for round to advance
        </div>
      )}

      {/* Focused slot */}
      <div>
        <p
          className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground"
          title="Your primary declared action this round, the technique or maneuver you're committing to."
        >
          Focused Action
        </p>
        <ActionDeclarationCard
          characterId={characterId}
          characterSheetId={characterSheetId}
          actionContext={focusedContext}
          onContextChange={(next) => {
            setSubmitError(null);
            setFocusedContext(next);
          }}
          readOnly={isLocked}
          targets={focusedTargets}
          reach={focusedTechniqueReach}
          actorPositionId={actorPositionId}
          positionAdjacency={encounter?.position_adjacency ?? []}
          positionTargetShape={focusedTechniquePositionShape}
          positions={focusedPositions}
          castPosition={castPosition}
          onCastPositionChange={setCastPosition}
          strainMax={strainMax}
        />
        {soulfrayWarning !== null && (
          <SoulfrayAcceptGate
            warning={soulfrayWarning}
            techniqueName={focusedCastDescriptor?.display_name ?? 'Cast'}
            animaCost={0}
            accepted={soulfrayAccepted}
            onAcceptChange={setSoulfrayAccepted}
            disabled={isLocked}
          />
        )}
        {soulfrayWarning === null && isWardBearingCast && (
          <label
            className="mt-1.5 flex items-center gap-2 rounded-md border border-amber-500/60 bg-amber-950/40 px-2 py-1.5 text-xs"
            data-testid="cast-ward-soulfray-gate"
          >
            <input
              type="checkbox"
              data-testid="cast-ward-soulfray-toggle"
              checked={soulfrayAccepted}
              onChange={(e) => setSoulfrayAccepted(e.target.checked)}
              disabled={isLocked}
            />
            <span>
              Hold this ward into Soulfray (fee {focusedCastDescriptor?.reactive_anima_cost} anima
              per fire)
            </span>
          </label>
        )}
        {furyTiers.length > 0 && (
          <FuryDeclaration
            tiers={furyTiers}
            anchors={furyAnchors}
            tierId={furyTierId}
            anchorId={furyAnchorId}
            onTierChange={setFuryTierId}
            onAnchorChange={setFuryAnchorId}
            disabled={isLocked}
          />
        )}
      </div>

      {/* Clash contribution subsection — shown when clash actions are available */}
      {clashActions.length > 0 && (
        <div className="space-y-2" data-testid="clash-contributions-section">
          <p
            className="text-xs font-semibold uppercase tracking-wide text-muted-foreground"
            title="Add strain to an ongoing team Clash instead of acting alone this round."
          >
            Clash Contributions
          </p>
          {clashActions.map((action) => {
            const clashId = action.ref.clash_id;
            if (clashId == null) return null;
            return (
              <ClashContributionRow
                key={clashId}
                action={action}
                strainCommitment={strainByClash[clashId] ?? 0}
                onSelectClash={(ref) => {
                  setSelectedClashRef(selectedClashRef?.clash_id === ref.clash_id ? null : ref);
                  // Update focused context with the strain commitment.
                  setFocusedContext((prev) => ({
                    ...prev,
                    strainCommitment: strainByClash[clashId] ?? 0,
                  }));
                }}
                onStrainChange={(value) => {
                  setStrainByClash((prev) => ({ ...prev, [clashId]: value }));
                  // Mirror to focusedContext.strainCommitment so the card sees it.
                  setFocusedContext((prev) => ({ ...prev, strainCommitment: value }));
                }}
                isSelected={selectedClashRef?.clash_id === clashId}
                strainMax={strainMax}
              />
            );
          })}
        </div>
      )}

      {/* Move-to-position actions (#532) — shown when adjacent open positions exist */}
      <MovementActions
        actions={moveActions}
        isLocked={isLocked}
        dispatchAction={dispatchAction}
        onDispatched={() => {
          queryClient
            .invalidateQueries({ queryKey: combatKeys.encounter(encounterId) })
            .catch(() => {});
        }}
      />

      {/* Passive slots — only non-focused-category slots */}
      {visiblePassiveSlots.length > 0 && (
        <div className="space-y-3">
          <p
            className="text-xs font-semibold uppercase tracking-wide text-muted-foreground"
            title="Secondary declarations in categories your Focused Action doesn't use; they resolve alongside it."
          >
            Passive Actions
          </p>
          {visiblePassiveSlots.map((slot) => (
            <ActionDeclarationCard
              key={slot}
              characterId={characterId}
              characterSheetId={characterSheetId}
              actionContext={passiveContexts[slot] ?? initialContext(slot)}
              onContextChange={(next) => {
                setSubmitError(null);
                setPassiveContexts((prev) => ({ ...prev, [slot]: next }));
              }}
              readOnly={isLocked}
            />
          ))}
        </div>
      )}

      {/* Combo upgrade row — shown when combos are available */}
      {availableCombos !== undefined && availableCombos.length > 0 && (
        <div className="space-y-2" data-testid="combo-upgrade-section">
          <p
            className="text-xs font-semibold uppercase tracking-wide text-muted-foreground"
            title="Upgrade your Focused Action into a known multi-slot combo, if you qualify this round."
          >
            Combo Upgrades
          </p>
          {availableCombos.map((combo) => (
            <ComboRow
              key={combo.combo_id}
              combo={combo}
              onUpgrade={(id) => upgradeCombo(id)}
              isLoading={combosLoading || upgradePending}
            />
          ))}
        </div>
      )}

      {/* Revert Combo — symmetric with the upgrade row above; visible only while
          this round's action has an active combo upgrade (#3381). */}
      {ownRoundAction?.combo_upgrade != null && (
        <button
          type="button"
          disabled={isLocked || maneuverDispatchPending}
          onClick={() => {
            handleRevertCombo().catch(() => {});
          }}
          data-testid="revert-combo-btn"
          className={cn(
            'w-full rounded-md border px-3 py-1.5 text-left text-xs font-medium transition-colors',
            'disabled:cursor-not-allowed disabled:opacity-50',
            isLocked
              ? 'border-border bg-muted text-muted-foreground'
              : 'border-amber-500/40 bg-amber-500/5 text-amber-300 hover:bg-amber-500/10'
          )}
        >
          {maneuverDispatchPending ? 'Reverting combo…' : 'Revert combo upgrade'}
        </button>
      )}

      <UseItemSection
        usableItems={usableItems}
        coverableAllies={coverableAllies}
        activeOpponents={activeOpponents}
        instanceId={useItemInstanceId}
        targetValue={useItemTargetValue}
        error={useItemError}
        disabled={isLocked || !isDeclaringPhase || maneuverDispatchPending}
        inactive={isLocked || !isDeclaringPhase}
        pending={maneuverDispatchPending}
        onInstanceChange={setUseItemInstanceId}
        onTargetChange={setUseItemTargetValue}
        onConfirm={() => {
          handleUseItem().catch(() => {});
        }}
      />

      {isMounted && (
        <MountedManeuvers
          activeOpponents={activeOpponents}
          physicalTechniques={physicalTechniques}
          chargeOpponentId={chargeOpponentId}
          chargeTechniqueId={chargeTechniqueId}
          chargeError={chargeError}
          joustTechniqueId={joustTechniqueId}
          joustError={joustError}
          isDuelEncounter={isDuelEncounter}
          disabled={isLocked || !isDeclaringPhase || maneuverDispatchPending}
          inactive={isLocked || !isDeclaringPhase}
          pending={maneuverDispatchPending}
          onChargeOpponentChange={setChargeOpponentId}
          onChargeTechniqueChange={setChargeTechniqueId}
          onJoustTechniqueChange={setJoustTechniqueId}
          onCharge={() => {
            handleCharge().catch(() => {});
          }}
          onJoust={() => {
            handleJoust().catch(() => {});
          }}
        />
      )}

      {/* Thread Pull row — inline pull selection for combat cast/clash dispatch */}
      <div
        className="space-y-1 rounded border border-primary/20 bg-primary/5 px-3 py-2"
        data-testid="thread-pull-row"
      >
        <div className="flex items-center justify-between">
          <span
            className="text-xs font-semibold text-primary/80"
            title="Draw on a bonded Thread to empower this round's action."
          >
            ✦ Thread Pull
          </span>
          <div className="flex gap-2">
            {selectedPull !== null && (
              <button
                type="button"
                onClick={() => setSelectedPull(null)}
                disabled={isLocked}
                data-testid="clear-pull-btn"
                className="rounded border border-destructive/40 bg-destructive/10 px-2 py-1 text-xs font-medium text-destructive transition-colors hover:bg-destructive/20 disabled:cursor-not-allowed disabled:opacity-50"
              >
                Clear
              </button>
            )}
            <button
              type="button"
              onClick={() => setPullDialogOpen(true)}
              disabled={isLocked}
              data-testid="open-pull-dialog-btn"
              className="rounded border border-primary/40 bg-primary/10 px-3 py-1 text-xs font-medium text-primary transition-colors hover:bg-primary/20 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {selectedPull === null ? 'Pull Threads' : 'Change Pull'}
            </button>
          </div>
        </div>
        {selectedPull !== null && (
          <p className="text-[10px] text-primary/70" data-testid="selected-pull-summary">
            Tier {selectedPull.tier} pull: {selectedPull.thread_ids.length} thread
            {selectedPull.thread_ids.length === 1 ? '' : 's'} selected
          </p>
        )}
      </div>

      <ThreadPullDialog
        characterSheetId={characterSheetId}
        open={pullDialogOpen}
        onClose={() => setPullDialogOpen(false)}
        onSelect={(selection) => {
          setSelectedPull(selection);
          setPullDialogOpen(false);
        }}
      />

      {/* Flee / Cover declaration cluster — always rendered when encounter is non-null; controls disabled outside the declaring phase */}
      {encounter != null && (
        <div className="space-y-2" data-testid="maneuver-declaration-section">
          <p
            className="text-xs font-semibold uppercase tracking-wide text-muted-foreground"
            title="Flee the encounter, Cover an ally, or Guard an ally with your body or a protective technique, instead of declaring an offensive or defensive action."
          >
            Maneuvers
          </p>

          <DeclaredManeuverBadge
            declaredManeuver={declaredManeuver}
            coveredAllyName={coveredAllyName}
            guardedAllyName={guardedAllyName}
          />

          {/* Flee button — only when not already declared a flee maneuver */}
          {declaredManeuver !== 'flee' && (
            <button
              type="button"
              disabled={isLocked || !isDeclaringPhase || fleePending}
              onClick={handleFlee}
              data-testid="flee-btn"
              className={cn(
                'w-full rounded-md border px-4 py-2 text-sm font-semibold transition-colors',
                'disabled:cursor-not-allowed disabled:opacity-50',
                isLocked || !isDeclaringPhase
                  ? 'border-border bg-muted text-muted-foreground'
                  : 'border-destructive bg-destructive/10 text-destructive hover:bg-destructive/20'
              )}
            >
              {fleePending ? 'Declaring flee…' : 'Flee'}
            </button>
          )}

          <CoverControl
            declaredManeuver={declaredManeuver}
            coverableAllies={coverableAllies}
            coverAllyId={coverAllyId}
            coverPending={coverPending}
            isLocked={isLocked}
            isDeclaringPhase={isDeclaringPhase}
            setCoverAllyId={setCoverAllyId}
            handleCover={handleCover}
          />

          {/* Guard control — ward picker + optional protective-technique select + confirm (#2207) */}
          <GuardControl
            declaredManeuver={declaredManeuver}
            encounter={encounter}
            guardControlRef={guardControlRef}
            coverableAllies={coverableAllies}
            protectiveTechniques={protectiveTechniques}
            selectedGuardTechnique={selectedGuardTechnique}
            isRedirectGuardTechnique={isRedirectGuardTechnique}
            guardAllyId={guardAllyId}
            guardTechniqueId={guardTechniqueId}
            guardDestination={guardDestination}
            guardSoulfrayAccepted={guardSoulfrayAccepted}
            animaCurrent={animaCurrent}
            guardPending={guardPending}
            isLocked={isLocked}
            isDeclaringPhase={isDeclaringPhase}
            setGuardAllyId={setGuardAllyId}
            setGuardTechniqueId={setGuardTechniqueId}
            setGuardDestination={setGuardDestination}
            setGuardSoulfrayAccepted={setGuardSoulfrayAccepted}
            handleGuard={handleGuard}
          />

          {/* Rally control — ally picker + confirm button (#3381) */}
          <div className="space-y-1.5" data-testid="rally-control">
            <Select
              value={rallyAllyId}
              onValueChange={setRallyAllyId}
              disabled={isLocked || !isDeclaringPhase || maneuverDispatchPending}
            >
              <SelectTrigger data-testid="rally-ally-select" className="h-8 text-xs">
                <SelectValue placeholder="Rally an ally…" />
              </SelectTrigger>
              <SelectContent>
                {coverableAllies.map((ally) => (
                  <SelectItem key={ally.id} value={String(ally.id)}>
                    {ally.character_name}
                  </SelectItem>
                ))}
                {coverableAllies.length === 0 && (
                  <SelectItem value="__none__" disabled>
                    No allies available
                  </SelectItem>
                )}
              </SelectContent>
            </Select>
            <button
              type="button"
              disabled={
                isLocked || !isDeclaringPhase || maneuverDispatchPending || rallyAllyId === ''
              }
              onClick={() => {
                handleRally().catch(() => {});
              }}
              data-testid="rally-confirm-btn"
              className={cn(
                'w-full rounded-md border px-4 py-1.5 text-xs font-semibold transition-colors',
                'disabled:cursor-not-allowed disabled:opacity-50',
                isLocked || !isDeclaringPhase || rallyAllyId === ''
                  ? 'border-border bg-muted text-muted-foreground'
                  : 'border-emerald-500/60 bg-emerald-500/10 text-emerald-300 hover:bg-emerald-500/20'
              )}
            >
              {maneuverDispatchPending ? 'Declaring rally…' : 'Rally'}
            </button>
          </div>

          {/* Succor control — shelter an ally from an environmental hazard (#3381, #1744) */}
          <div className="space-y-1.5" data-testid="succor-control">
            <Select
              value={succorAllyId}
              onValueChange={setSuccorAllyId}
              disabled={isLocked || !isDeclaringPhase || maneuverDispatchPending}
            >
              <SelectTrigger data-testid="succor-ally-select" className="h-8 text-xs">
                <SelectValue placeholder="Shelter an ally…" />
              </SelectTrigger>
              <SelectContent>
                {coverableAllies.map((ally) => (
                  <SelectItem key={ally.id} value={String(ally.id)}>
                    {ally.character_name}
                  </SelectItem>
                ))}
                {coverableAllies.length === 0 && (
                  <SelectItem value="__none__" disabled>
                    No allies available
                  </SelectItem>
                )}
              </SelectContent>
            </Select>
            <button
              type="button"
              disabled={
                isLocked || !isDeclaringPhase || maneuverDispatchPending || succorAllyId === ''
              }
              onClick={() => {
                handleSuccor().catch(() => {});
              }}
              data-testid="succor-confirm-btn"
              className={cn(
                'w-full rounded-md border px-4 py-1.5 text-xs font-semibold transition-colors',
                'disabled:cursor-not-allowed disabled:opacity-50',
                isLocked || !isDeclaringPhase || succorAllyId === ''
                  ? 'border-border bg-muted text-muted-foreground'
                  : 'border-sky-500/60 bg-sky-500/10 text-sky-300 hover:bg-sky-500/20'
              )}
            >
              {maneuverDispatchPending ? 'Declaring succor…' : 'Succor'}
            </button>
          </div>

          {/* Maneuver error display */}
          {maneuverError !== null && (
            <p role="alert" className="text-sm text-destructive" data-testid="maneuver-error">
              {maneuverError}
            </p>
          )}
        </div>
      )}

      {/* Submit declarations button */}
      <button
        type="button"
        disabled={
          isLocked ||
          dispatchPending ||
          (soulfrayWarning !== null && !soulfrayAccepted) ||
          furyOverCap ||
          !positionRequirementMet
        }
        onClick={() => {
          handleSubmit().catch(() => {});
        }}
        data-testid="submit-declarations-btn"
        className={cn(
          'w-full rounded-md border px-4 py-2 text-sm font-semibold transition-colors',
          'disabled:cursor-not-allowed disabled:opacity-50',
          isLocked
            ? 'border-border bg-muted text-muted-foreground'
            : 'border-primary bg-primary text-primary-foreground hover:bg-primary/90'
        )}
      >
        {renderDispatch()}
      </button>

      {/* Inline submit error — shown when a dispatch rejects */}
      {submitError !== null && (
        <p role="alert" className="mt-2 text-sm text-destructive">
          {submitError}
        </p>
      )}
    </div>
  );
}

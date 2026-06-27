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

import { useEffect, useState } from 'react';
import { cn } from '@/lib/utils';
import { ActionDeclarationCard } from '@/actions/ActionDeclarationCard';
import type { ActionContext, ActionSlot, EffortLevel, TargetOption } from '@/actions/types';
import type { PlayerAction, SoulfrayWarningData } from '@/scenes/actionTypes';
import { MovementActions } from '../components/MovementActions';
import { SoulfrayAcceptGate } from '../components/SoulfrayAcceptGate';
import { FuryDeclaration } from '../components/FuryDeclaration';
import { ThreadPullDialog, type PullSelection } from '@/magic/components/threads/ThreadPullDialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  useAvailableCombos,
  useCoverMutation,
  useDispatchPlayerAction,
  useFleeMutation,
  useUpgradeCombo,
} from '../queries';
import type {
  AvailableCombo,
  DispatchActionRequest,
  EncounterDetail,
  Participant,
  RoundActionTyped,
} from '../types';

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
// Dispatch-job builders (extracted from handleSubmit to flatten its branching)
// ---------------------------------------------------------------------------

type DispatchFn = (params: DispatchActionRequest) => Promise<unknown>;

type DispatchJob = () => Promise<unknown>;

/**
 * Build the focused-slot dispatch job (if a technique is selected). Threads the
 * chosen single target onto the focused declaration (#1001a); the backend
 * resolves these PKs to instances scoped to the encounter.
 *
 * When a pull is selected, pull_resonance_id / pull_tier / pull_thread_ids are
 * merged into kwargs so the backend commits a CombatPull alongside the action.
 */
function buildFocusedJob(
  focusedContext: ActionContext,
  effortLevel: string,
  dispatchAction: DispatchFn,
  selectedPull: PullSelection | null,
  soulfrayAccepted: boolean,
  soulfrayWarning: SoulfrayWarningData | null,
  furyTierId: number | null,
  furyAnchorId: number | null
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
    soulfrayWarning !== null && soulfrayAccepted ? { confirm_soulfray_risk: true } : {};

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
        ...furyKwargs,
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
}: YourTurnProps) {
  const strainMax = availableStrain ?? 10;
  // ---------------------------------------------------------------------------
  // Slot state
  // ---------------------------------------------------------------------------

  const [focusedContext, setFocusedContext] = useState<ActionContext>(() =>
    initialContext('focused')
  );
  const [passiveContexts, setPassiveContexts] = useState<
    Partial<Record<ActionSlot, ActionContext>>
  >(() => ({
    'passive-physical': initialContext('passive-physical'),
    'passive-social': initialContext('passive-social'),
    'passive-mental': initialContext('passive-mental'),
  }));

  // ---------------------------------------------------------------------------
  // Clash selection state
  // ---------------------------------------------------------------------------

  // Currently-selected clash ref (for the focused slot target).
  const [selectedClashRef, setSelectedClashRef] = useState<PlayerAction['ref'] | null>(null);
  // Per-clash strain commitment. Keyed on clash_id.
  const [strainByClash, setStrainByClash] = useState<Record<number, number>>({});

  // ---------------------------------------------------------------------------
  // Submit state
  // ---------------------------------------------------------------------------

  const [submitted, setSubmitted] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [pullDialogOpen, setPullDialogOpen] = useState(false);
  // Inline pull selection — populated when the player selects a pull via the
  // ThreadPullDialog. Sent in kwargs of the focused/clash dispatch on submit.
  const [selectedPull, setSelectedPull] = useState<PullSelection | null>(null);

  // Soulfray + fury declaration state for combat-cast focused actions (#1543).
  const [soulfrayAccepted, setSoulfrayAccepted] = useState(false);
  const [furyTierId, setFuryTierId] = useState<number | null>(null);
  const [furyAnchorId, setFuryAnchorId] = useState<number | null>(null);

  // Cover picker state — selected ally participant PK (string for Select compatibility).
  const [coverAllyId, setCoverAllyId] = useState<string>('');
  const [maneuverError, setManeuverError] = useState<string | null>(null);

  // Reset submitted, pull selection, and pull dialog when round advances.
  useEffect(() => {
    setSubmitted(false);
    setPullDialogOpen(false);
    setSelectedPull(null);
    setSoulfrayAccepted(false);
    setFuryTierId(null);
    setFuryAnchorId(null);
    setCoverAllyId('');
    setManeuverError(null);
  }, [roundNumber]);

  // ---------------------------------------------------------------------------
  // Slot composition
  // ---------------------------------------------------------------------------

  const focusedCategory = resolveFocusedCategory(focusedContext, availableActions);
  const visiblePassiveSlots = passiveSlotsToRender(focusedCategory);

  // ---------------------------------------------------------------------------
  // Clash actions from availableActions (COMBAT backend + clash_id set)
  // ---------------------------------------------------------------------------

  const clashActions = availableActions.filter(
    (a) => a.ref.backend === 'COMBAT' && a.ref.clash_id != null
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

  const participants: Participant[] = encounter?.participants ?? [];

  // All active participants except self count as allies until covenant sides land (mirrors backend serializers.py note).
  const coverableAllies = participants.filter(
    (p) => p.status === 'active' && p.id !== myParticipantId
  );

  // Actor's position — the viewer's own participant's current_position.
  const actorPositionId: number | null = (() => {
    if (myParticipantId === null) return null;
    const self = (encounter?.participants ?? []).find((p) => p.id === myParticipantId);
    return self?.current_position?.id ?? null;
  })();

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

  // Reach constraint for the currently selected focused technique (#532).
  const focusedTechniqueReach: string | null = (() => {
    if (focusedContext.techniqueId === undefined) return null;
    const selected = availableActions.find(
      (a) => a.ref.technique_id === focusedContext.techniqueId
    );
    return selected?.reach ?? null;
  })();

  // Soulfray + fury descriptor for the currently selected focused cast (#1543).
  const focusedCastDescriptor = (() => {
    if (focusedContext.techniqueId === undefined) return null;
    return availableActions.find((a) => a.ref.technique_id === focusedContext.techniqueId) ?? null;
  })();
  const soulfrayWarning = focusedCastDescriptor?.soulfray_warning ?? null;
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
  const coveredAllyName = (() => {
    if (declaredManeuver !== 'cover' || ownRoundAction?.focused_ally_target == null) return null;
    const ally = participants.find((p) => p.id === ownRoundAction.focused_ally_target);
    return ally?.character_name ?? `participant #${ownRoundAction.focused_ally_target}`;
  })();

  // ---------------------------------------------------------------------------
  // Dispatch
  // ---------------------------------------------------------------------------

  const { mutateAsync: dispatchAction, isPending: dispatchPending } =
    useDispatchPlayerAction(characterId);

  // ---------------------------------------------------------------------------
  // Submit handler
  // ---------------------------------------------------------------------------

  async function handleSubmit() {
    if (submitted || dispatchPending) return;

    setSubmitError(null);

    if (soulfrayWarning !== null && !soulfrayAccepted) {
      setSubmitError('Accept the Soulfray risk to proceed.');
      return;
    }
    if (furyOverCap) {
      setSubmitError('Chosen fury tier exceeds your bond with the anchor.');
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
      furyAnchorId
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
        await job();
      }
      setSubmitted(true);
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

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  const isLocked = readOnly || submitted;

  return (
    <div className="space-y-4" data-testid="your-turn-section">
      {/* Submitted / ready badge */}
      {submitted && (
        <div
          className="rounded-md border border-emerald-500/40 bg-emerald-500/10 px-3 py-2 text-center text-sm font-medium text-emerald-300"
          data-testid="ready-badge"
        >
          Ready — waiting for round to advance
        </div>
      )}

      {/* Focused slot */}
      <div>
        <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
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
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
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
      <MovementActions actions={moveActions} isLocked={isLocked} dispatchAction={dispatchAction} />

      {/* Passive slots — only non-focused-category slots */}
      {visiblePassiveSlots.length > 0 && (
        <div className="space-y-3">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
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
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
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

      {/* Thread Pull row — inline pull selection for combat cast/clash dispatch */}
      <div
        className="space-y-1 rounded border border-primary/20 bg-primary/5 px-3 py-2"
        data-testid="thread-pull-row"
      >
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold text-primary/80">✦ Thread Pull</span>
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
            Tier {selectedPull.tier} pull — {selectedPull.thread_ids.length} thread
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
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Maneuvers
          </p>

          {/* Declared-state display */}
          {declaredManeuver === 'flee' && (
            <div
              className="rounded border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-300"
              data-testid="flee-declared-badge"
            >
              Fleeing — resolves at end of round
            </div>
          )}
          {declaredManeuver === 'cover' && (
            <div
              className="rounded border border-sky-500/40 bg-sky-500/10 px-3 py-2 text-xs text-sky-300"
              data-testid="cover-declared-badge"
            >
              Covering {coveredAllyName ?? 'ally'}
            </div>
          )}

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

          {/* Cover control — ally picker + confirm button */}
          {declaredManeuver !== 'cover' && (
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
          )}

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
          furyOverCap
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
        {dispatchPending ? 'Submitting…' : 'Submit declarations · mark ready'}
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

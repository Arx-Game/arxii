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
import type { ActionContext, ActionSlot } from '@/actions/types';
import type { PlayerAction } from '@/scenes/actionTypes';
import { useAvailableCombos, useDispatchPlayerAction, useUpgradeCombo } from '../queries';
import type { AvailableCombo } from '../types';

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
}

// ---------------------------------------------------------------------------
// Passive slot categories
// ---------------------------------------------------------------------------

const PASSIVE_SLOTS: ActionSlot[] = [
  'passive-physical',
  'passive-social',
  'passive-mental',
];

/**
 * Derive the category of the focused slot from the selected technique.
 *
 * TODO(phase-7-follow-up): The technique's category (Physical/Social/Mental)
 * is not currently surfaced in the PlayerAction descriptor or the available
 * actions response — ActionRef only carries technique_id. A richer typing
 * phase should expose `effect_type.category` or `style.category` in the
 * PlayerAction so this can be derived without a separate fetch.
 *
 * For Phase 7, we stub the focused category as 'physical' so the slot
 * composition logic has something concrete to work with. The real slot
 * category is computed in a follow-up when the API exposes it.
 */
function resolveFocusedCategory(_context: ActionContext): ActionSlot | null {
  // Stub: always return 'physical' so passive-physical is hidden.
  // Follow-up: derive from technique.effect_type.category or technique.style.category.
  return 'passive-physical';
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
        'w-full rounded border px-3 py-1.5 text-xs font-medium text-left transition-colors',
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
}

function ClashContributionRow({
  action,
  strainCommitment,
  onSelectClash,
  onStrainChange,
  isSelected,
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
          'w-full rounded px-2 py-1 text-xs font-medium text-left transition-colors',
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
            <span className="text-[10px] text-muted-foreground uppercase tracking-wide">
              Strain commitment
            </span>
            <span className="text-xs font-mono text-foreground">{strainCommitment}</span>
          </div>
          <input
            type="range"
            min={0}
            max={10}
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
}: YourTurnProps) {
  // ---------------------------------------------------------------------------
  // Slot state
  // ---------------------------------------------------------------------------

  const [focusedContext, setFocusedContext] = useState<ActionContext>(
    () => initialContext('focused')
  );
  const [passiveContexts, setPassiveContexts] = useState<Record<ActionSlot, ActionContext>>(
    () => ({
      'passive-physical': initialContext('passive-physical'),
      'passive-social': initialContext('passive-social'),
      'passive-mental': initialContext('passive-mental'),
    })
  );

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

  // Reset submitted when round advances.
  useEffect(() => {
    setSubmitted(false);
  }, [roundNumber]);

  // ---------------------------------------------------------------------------
  // Slot composition
  // ---------------------------------------------------------------------------

  const focusedCategory = resolveFocusedCategory(focusedContext);
  const visiblePassiveSlots = passiveSlotsToRender(focusedCategory);

  // ---------------------------------------------------------------------------
  // Clash actions from availableActions (COMBAT backend + clash_id set)
  // ---------------------------------------------------------------------------

  const clashActions = availableActions.filter(
    (a) => a.ref.backend === 'COMBAT' && a.ref.clash_id !== null
  );

  // ---------------------------------------------------------------------------
  // Combos
  // ---------------------------------------------------------------------------

  const { data: availableCombos, isLoading: combosLoading } = useAvailableCombos(encounterId);
  const { mutate: upgradeCombo, isPending: upgradePending } = useUpgradeCombo(encounterId);

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

    // Submission order per plan: focused first, then passives, then clashes.
    const dispatchJobs: Array<() => Promise<unknown>> = [];

    // 1. Focused action (if technique selected)
    if (focusedContext.techniqueId !== undefined) {
      dispatchJobs.push(() =>
        dispatchAction({
          ref: {
            backend: 'COMBAT',
            technique_id: focusedContext.techniqueId ?? null,
          },
          kwargs: {},
        })
      );
    }

    // 2. Passive actions (for each visible passive slot that has a technique)
    for (const slot of visiblePassiveSlots) {
      const ctx = passiveContexts[slot];
      if (ctx.techniqueId !== undefined) {
        dispatchJobs.push(() =>
          dispatchAction({
            ref: {
              backend: 'COMBAT',
              technique_id: ctx.techniqueId ?? null,
            },
            kwargs: {},
          })
        );
      }
    }

    // 3. Clash contributions — technique_id goes in kwargs (NOT on the ref).
    // Per plan Task 7.3: ActionRef.__post_init__ rejects both clash_id and
    // technique_id being set; see src/actions/types.py:137-155.
    if (selectedClashRef !== null && selectedClashRef.clash_id !== null) {
      const clashId = selectedClashRef.clash_id;
      const strain = strainByClash[clashId] ?? 0;
      dispatchJobs.push(() =>
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
          },
        })
      );
    }

    // Execute in order (focused first guarantees the server sees focused before passives).
    for (const job of dispatchJobs) {
      await job();
    }

    setSubmitted(true);
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
          className="rounded-md border border-emerald-500/40 bg-emerald-500/10 px-3 py-2 text-sm font-medium text-emerald-300 text-center"
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
          onContextChange={setFocusedContext}
          readOnly={isLocked}
        />
      </div>

      {/* Clash contribution subsection — shown when clash actions are available */}
      {clashActions.length > 0 && (
        <div
          className="space-y-2"
          data-testid="clash-contributions-section"
        >
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Clash Contributions
          </p>
          {clashActions.map((action) => {
            const clashId = action.ref.clash_id;
            if (clashId === null) return null;
            return (
              <ClashContributionRow
                key={clashId}
                action={action}
                strainCommitment={strainByClash[clashId] ?? 0}
                onSelectClash={(ref) => {
                  setSelectedClashRef(
                    selectedClashRef?.clash_id === ref.clash_id ? null : ref
                  );
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
              />
            );
          })}
        </div>
      )}

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
              actionContext={passiveContexts[slot]}
              onContextChange={(next) =>
                setPassiveContexts((prev) => ({ ...prev, [slot]: next }))
              }
              readOnly={isLocked}
            />
          ))}
        </div>
      )}

      {/* Lend-to-clash stub — deferred wiring, Phase 7 placeholder */}
      <div className="rounded border border-dashed border-border/40 p-2">
        <button
          type="button"
          disabled
          title="lend-to-clash will dispatch a CLASH_SUPPORT action"
          // TODO(phase-7-deferred): Wire CLASH_SUPPORT dispatch path when backend
          // exposes it as a PlayerAction descriptor. Backend dispatch handler for
          // CLASH_SUPPORT does not exist yet as of Phase 7.
          className="w-full cursor-not-allowed rounded px-2 py-1 text-xs text-muted-foreground opacity-50"
          data-testid="lend-to-clash-stub"
        >
          Lend to clash (not yet available)
        </button>
      </div>

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

      {/* Submit declarations button */}
      <button
        type="button"
        disabled={isLocked || dispatchPending}
        onClick={() => { void handleSubmit(); }}
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
    </div>
  );
}

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
 * - Effort selector, I/C chip, cost preview — Task 5.3.
 */

import { useQuery } from '@tanstack/react-query';
import { cn } from '@/lib/utils';
import { fetchAvailableActions } from '@/scenes/actionQueries';
import type { PlayerAction } from '@/scenes/actionTypes';
import type { ActionContext } from './types';

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

  const hasTechnique = actionContext.techniqueId !== undefined;

  return (
    <div className="rounded-lg border border-border bg-card p-4 shadow-sm space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold capitalize">
          {actionContext.slot.replace(/-/g, ' ')}
        </h3>
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

      {/* Effort section — placeholder; selectable pills added in Task 5.3 */}
      <Section label="Effort">
        <p className="text-xs text-muted-foreground">{actionContext.effort}</p>
      </Section>

      {/* Cost section */}
      <Section label="Cost">
        <p className="text-xs text-muted-foreground">
          {hasTechnique ? 'Calculating...' : '— select a technique first —'}
        </p>
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

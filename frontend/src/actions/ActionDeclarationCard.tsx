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
 * - Technique + target pickers — Task 5.2.
 * - Effort selector, I/C chip, cost preview — Task 5.3.
 */

import { cn } from '@/lib/utils';
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
  characterId: _characterId,
  actionContext,
  onContextChange: _onContextChange,
  readOnly: _readOnly = false,
}: ActionDeclarationCardProps) {
  const hasTechnique = actionContext.techniqueId !== undefined;

  return (
    <div className={cn('rounded-lg border border-border bg-card p-4 shadow-sm space-y-4')}>
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold capitalize">
          {actionContext.slot.replace(/-/g, ' ')}
        </h3>
      </div>

      {/* Technique section */}
      <Section label="Technique">
        {hasTechnique ? (
          <p className="text-xs text-muted-foreground">Technique #{actionContext.techniqueId}</p>
        ) : (
          <p className="text-xs text-muted-foreground italic">Pick a technique</p>
        )}
      </Section>

      {/* Target section */}
      <Section label="Target">
        <p className="text-xs text-muted-foreground">— no target selected —</p>
      </Section>

      {/* Effort section */}
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

/**
 * ResonanceBudget — rail section showing per-resonance balance bars.
 *
 * Uses useCharacterResonances(characterSheetId) for balances.
 * Hover on each row surfaces the existing <ResonanceBalanceCard>.
 *
 * Phase 8, Task 8.1 — unified-combat-ui plan.
 */

import { cn } from '@/lib/utils';
import { HoverCard, HoverCardContent, HoverCardTrigger } from '@/components/ui/hover-card';
import { useCharacterResonances } from '@/magic/queries';
import type { CharacterResonance } from '@/magic/types';

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface ResonanceBudgetProps {
  characterSheetId: number;
  /** Whether the section is collapsed. Controlled by parent (Task 8.6). */
  collapsed?: boolean;
  onToggleCollapse?: () => void;
}

// ---------------------------------------------------------------------------
// ResonanceRow — one resonance with bar + numeric, hover shows detail card
// ---------------------------------------------------------------------------

interface ResonanceRowProps {
  resonance: CharacterResonance;
}

function ResonanceRow({ resonance }: ResonanceRowProps) {
  const balance = resonance.balance ?? 0;
  const lifetime = resonance.lifetime_earned ?? 0;
  // Bar fills based on balance vs lifetime_earned (0 when no lifetime yet)
  const fillPct = lifetime > 0 ? Math.min(100, (balance / lifetime) * 100) : 0;
  const name = resonance.resonance_name;

  const rowContent = (
    <div className="space-y-1" data-testid={`resonance-row-${resonance.id}`}>
      <div className="flex items-center justify-between">
        <span className="truncate text-xs text-foreground">{name}</span>
        <span className="ml-2 shrink-0 font-mono text-xs text-foreground">
          {balance}
          <span className="text-muted-foreground"> / {lifetime}</span>
        </span>
      </div>
      {/* Current/spent bar */}
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
        <div
          className="h-full rounded-full bg-primary transition-all"
          style={{ width: `${fillPct}%` }}
          data-testid={`resonance-bar-${resonance.id}`}
        />
      </div>
    </div>
  );

  const flavorText = resonance.flavor_text;

  if (!flavorText) {
    return rowContent;
  }

  return (
    <HoverCard>
      <HoverCardTrigger asChild>
        <div className="cursor-default">{rowContent}</div>
      </HoverCardTrigger>
      <HoverCardContent className="w-56 text-sm" data-testid="resonance-hover-detail">
        <p className="font-medium text-foreground">{name}</p>
        <p className="mt-1 text-xs text-muted-foreground">{flavorText}</p>
        <p className="mt-1 text-xs text-muted-foreground">
          Balance: {balance} &middot; Lifetime: {lifetime}
        </p>
      </HoverCardContent>
    </HoverCard>
  );
}

// ---------------------------------------------------------------------------
// ResonanceBudget
// ---------------------------------------------------------------------------

export function ResonanceBudget({
  characterSheetId,
  collapsed = false,
  onToggleCollapse,
}: ResonanceBudgetProps) {
  const { data: resonances, isLoading, isError } = useCharacterResonances(characterSheetId);

  return (
    <div className="rounded-md border border-border bg-card" data-testid="resonance-budget-section">
      {/* Section header */}
      <button
        type="button"
        onClick={onToggleCollapse}
        className="flex w-full items-center justify-between px-3 py-2 text-left"
        aria-expanded={!collapsed}
        data-testid="resonance-budget-toggle"
      >
        <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Resonance Budget
        </span>
        <span
          className={cn(
            'text-muted-foreground transition-transform',
            collapsed ? '-rotate-90' : 'rotate-0'
          )}
          aria-hidden="true"
        >
          ▾
        </span>
      </button>

      {/* Content — hidden when collapsed */}
      {!collapsed && (
        <div className="space-y-3 border-t border-border px-3 py-2">
          {isLoading && (
            <p className="text-xs text-muted-foreground" data-testid="resonance-loading">
              Loading…
            </p>
          )}
          {isError && (
            <p className="text-xs text-destructive" data-testid="resonance-error">
              Failed to load resonances.
            </p>
          )}
          {!isLoading && !isError && resonances !== undefined && resonances.length === 0 && (
            <p className="text-xs text-muted-foreground" data-testid="resonance-empty">
              No resonances claimed.
            </p>
          )}
          {!isLoading &&
            !isError &&
            resonances !== undefined &&
            resonances.map((r) => <ResonanceRow key={r.id} resonance={r} />)}
        </div>
      )}
    </div>
  );
}

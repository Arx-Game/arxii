/**
 * PoseUnitDetailPanel — lazy-fetched outcome details panel for a set of
 * ACTION Interactions.
 *
 * Fetches from GET /api/combat/action-outcome-details/?action_interaction_ids=N,M,...
 * when rendered. Collapsed by default; triggered by PoseUnit's expand state.
 *
 * Phase 9, Task 9.4.
 */

import { useOutcomeDetails } from '@/combat/queries';
import { PowerLedgerPanel } from '@/magic/components/PowerLedgerPanel';
import { cn } from '@/lib/utils';
import { useAppDispatch } from '@/store/hooks';
import { openDeepLink, type DeepLinkKind } from '@/store/deepLinkModalSlice';

interface EffectRow {
  kind: string;
  label: string;
  is_critical: boolean;
  deep_link: { modal: string; id: number } | null;
}

// Left-accent + tint applied to critical (KO/death/defeat) effect rows. (#996)
const CRITICAL_ROW = 'border-l-2 border-rose-500 bg-rose-500/10 pl-1.5';

interface PoseUnitDetailPanelProps {
  actionInteractionIds: number[];
}

export function PoseUnitDetailPanel({ actionInteractionIds }: PoseUnitDetailPanelProps) {
  const dispatch = useAppDispatch();
  const { data, isLoading, isError } = useOutcomeDetails(actionInteractionIds);

  if (isLoading) {
    return (
      <div
        className="mt-2 rounded border bg-muted/30 p-3 text-xs text-muted-foreground"
        data-testid="pose-unit-detail-panel"
      >
        Loading outcome details...
      </div>
    );
  }

  if (isError) {
    return (
      <div className="mt-2 rounded border bg-muted/30 p-3" data-testid="pose-unit-detail-panel">
        <p role="alert" className="text-sm text-destructive">
          Failed to load outcome details.
        </p>
      </div>
    );
  }

  if (!data || data.length === 0) {
    return (
      <div
        className="mt-2 rounded border bg-muted/30 p-3 text-xs text-muted-foreground"
        data-testid="pose-unit-detail-panel"
      >
        No outcome details available.
      </div>
    );
  }

  return (
    <div
      className="mt-2 space-y-2 rounded border bg-muted/30 p-3"
      data-testid="pose-unit-detail-panel"
    >
      {data.map((actionOutcome) => (
        <div key={actionOutcome.action_interaction_id} className="space-y-1">
          {actionOutcome.effects.length === 0 ? (
            <p className="text-xs text-muted-foreground">No recorded effects.</p>
          ) : (
            actionOutcome.effects.map((effect: EffectRow, idx: number) =>
              effect.deep_link != null ? (
                <button
                  key={idx}
                  type="button"
                  onClick={() =>
                    dispatch(
                      openDeepLink({
                        modal: effect.deep_link!.modal as DeepLinkKind,
                        id: effect.deep_link!.id,
                      })
                    )
                  }
                  className={cn(
                    'flex w-full items-start gap-1.5 text-left text-xs',
                    'cursor-pointer rounded hover:bg-muted/60',
                    effect.is_critical && CRITICAL_ROW
                  )}
                  data-critical={effect.is_critical || undefined}
                >
                  <EffectKindBadge kind={effect.kind} />
                  <span>{effect.label}</span>
                </button>
              ) : (
                <div
                  key={idx}
                  className={cn(
                    'flex items-start gap-1.5 text-xs',
                    effect.is_critical && CRITICAL_ROW
                  )}
                  data-critical={effect.is_critical || undefined}
                >
                  <EffectKindBadge kind={effect.kind} />
                  <span>{effect.label}</span>
                </div>
              )
            )
          )}
          {typeof actionOutcome.progress_delta === 'number' && (
            <ClashContributionStory
              strainCommitted={actionOutcome.strain_committed}
              power={actionOutcome.power}
              progressDelta={actionOutcome.progress_delta}
            />
          )}
          {actionOutcome.power_ledger && <PowerLedgerPanel ledger={actionOutcome.power_ledger} />}
        </div>
      ))}
    </div>
  );
}

// Clash contribution summary line: strain → power → progress. The power-ledger
// card below it carries the intensity/multiplier breakdown; this is the one-line
// story. `power` is gated to null for viewers who can't see the ledger, so it is
// omitted (strain + progress remain). Negative progress is a botch-backfire and
// renders as a loss. (#977)
function ClashContributionStory({
  strainCommitted,
  power,
  progressDelta,
}: {
  strainCommitted?: number | null;
  power?: number | null;
  progressDelta: number;
}) {
  const isLoss = progressDelta < 0;
  return (
    <div
      data-testid="clash-contribution-story"
      className="flex flex-wrap items-baseline gap-1 font-mono text-xs"
    >
      {strainCommitted != null && (
        <>
          <span>{strainCommitted} strain</span>
          <Arrow />
        </>
      )}
      {power != null && (
        <>
          <span>{power} power</span>
          <Arrow />
        </>
      )}
      <span
        data-testid="clash-progress-delta"
        className={cn('font-medium', isLoss ? 'text-rose-400' : 'text-emerald-400')}
      >
        {progressDelta >= 0 ? '+' : ''}
        {progressDelta} progress
      </span>
    </div>
  );
}

function Arrow() {
  return (
    <span aria-hidden className="text-muted-foreground">
      →
    </span>
  );
}

function EffectKindBadge({ kind }: { kind: string }) {
  // Effect kinds emitted by the outcome-details endpoint:
  //   combo, condition, status, clash_progress, anima, audere, soulfray
  //   (plus legacy: damage, trigger_fire, resource_change)
  const colorMap: Record<string, string> = {
    damage: 'text-red-400',
    condition: 'text-amber-400',
    combo: 'text-emerald-400',
    status: 'text-rose-400',
    clash_progress: 'text-cyan-400',
    anima: 'text-blue-400',
    audere: 'text-fuchsia-400',
    soulfray: 'text-violet-400',
    trigger_fire: 'text-purple-400',
    resource_change: 'text-blue-400',
  };
  const color = colorMap[kind] ?? 'text-muted-foreground';
  // Display labels: replace underscores with spaces for readability.
  const display = kind.replace(/_/g, ' ');
  return <span className={cn('shrink-0 font-medium capitalize', color)}>{display}</span>;
}

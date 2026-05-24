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
import { cn } from '@/lib/utils';

interface EffectRow {
  kind: string;
  label: string;
  deep_link: { modal: string; id: number } | null;
}

interface PoseUnitDetailPanelProps {
  actionInteractionIds: number[];
}

export function PoseUnitDetailPanel({ actionInteractionIds }: PoseUnitDetailPanelProps) {
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
      <div
        className="mt-2 rounded border bg-muted/30 p-3"
        data-testid="pose-unit-detail-panel"
      >
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
            actionOutcome.effects.map((effect: EffectRow, idx: number) => (
              <div key={idx} className={cn('flex items-start gap-1.5 text-xs')}>
                <EffectKindBadge kind={effect.kind} />
                <span>{effect.label}</span>
              </div>
            ))
          )}
        </div>
      ))}
    </div>
  );
}

function EffectKindBadge({ kind }: { kind: string }) {
  const colorMap: Record<string, string> = {
    damage: 'text-red-400',
    condition: 'text-amber-400',
    trigger_fire: 'text-purple-400',
    resource_change: 'text-blue-400',
  };
  const color = colorMap[kind] ?? 'text-muted-foreground';
  return <span className={cn('shrink-0 font-medium capitalize', color)}>{kind}</span>;
}

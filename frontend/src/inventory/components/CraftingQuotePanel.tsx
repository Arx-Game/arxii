/**
 * CraftingQuotePanel — cost / skill-cap / failure-risk summary for a crafting quote.
 *
 * Shared by AttachFacetDialog (facet/style attach) and CreateItemDialog (mint),
 * which quote through the same build_crafting_quote seam (#1031, #2240).
 */

import type { CraftingQuote } from '../api';
import { LabStationStatusCard } from './LabStationStatusCard';

const CONSUMPTION_LABELS: Record<string, string> = {
  none: 'nothing lost',
  partial: 'some materials/effort lost',
  full: 'all materials & effort lost',
};

interface CraftingQuotePanelProps {
  isLoading: boolean;
  quote: CraftingQuote | undefined;
  /** Forwarded to `LabStationStatusCard` — invalidate the caller's quote cache on repair. */
  onStationRepaired?: () => void;
}

export function CraftingQuotePanel({
  isLoading,
  quote,
  onStationRepaired,
}: CraftingQuotePanelProps) {
  if (isLoading) {
    return <p className="text-xs text-muted-foreground">Loading cost estimate…</p>;
  }
  if (!quote) return null;

  const { costs, affordable, max_quality_tier, failure_risk } = quote;

  const costParts: string[] = [];
  if (costs.action_points > 0) {
    costParts.push(`${costs.action_points_have}/${costs.action_points} AP`);
  }
  if (costs.anima > 0) {
    costParts.push(`${costs.anima_have}/${costs.anima} Anima`);
  }
  for (const mat of costs.materials) {
    costParts.push(`${mat.have}/${mat.quantity_required} ${mat.name}`);
  }

  return (
    <div
      className="space-y-1 rounded-md border bg-muted/40 px-3 py-2 text-sm"
      data-testid="crafting-quote-panel"
    >
      {costParts.length > 0 && (
        <p>
          <span className="font-medium">Costs:</span>{' '}
          <span className={affordable ? '' : 'text-destructive'}>{costParts.join(' · ')}</span>
        </p>
      )}
      {max_quality_tier != null ? (
        <p>
          <span className="font-medium">Skill cap:</span> {max_quality_tier.name}
        </p>
      ) : (
        <p className="text-muted-foreground">No skill cap</p>
      )}
      {failure_risk.length > 0 && (
        <p>
          <span className="font-medium">On failure:</span>{' '}
          {failure_risk
            .map((r) => r.label ?? CONSUMPTION_LABELS[r.cost_consumption] ?? r.cost_consumption)
            .join(', ')}
        </p>
      )}
      {quote.station_status && (
        <LabStationStatusCard
          featureInstanceId={quote.station_status.feature_instance_id}
          onRepaired={onStationRepaired}
        />
      )}
    </div>
  );
}

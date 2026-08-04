/**
 * TechniqueEffectSummaryDisplay — the ONE shared renderer for a technique's
 * effect summary (#2898).
 *
 * Backed by `TechniqueEffectSummary` (`@/magic/types`), which every technique
 * surface now carries: CG's `CGTechniqueOption`, the in-scene cast list's
 * `CastableTechnique`, the character sheet's `CharacterSheetTechnique`, and
 * the magic API's `Technique`. Before #2898 each of those four surfaces
 * hand-rolled its own rendering of a technique's cost/reach/targeting/
 * hostility (or, in CG and the cast list, rendered none of it at all) — this
 * component is the single place that logic lives now.
 *
 * The `summary` sentence is authored server-side and is identical over
 * telnet — it is always rendered verbatim as the primary line, never
 * re-derived or re-worded here.
 */

import { AlertTriangle } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import type { TechniqueEffectSummary } from '../types';

interface TechniqueEffectSummaryDisplayProps {
  summary: TechniqueEffectSummary;
  /**
   * "compact" — a single line, for dense lists (the cast-list rows, the
   * entrance-technique popover). "full" — the summary line plus secondary
   * chips for applies/removes/damage/grants, for detail panels (the selected-
   * technique panel, CG, the character sheet).
   */
  variant?: 'compact' | 'full';
  className?: string;
}

function damageEffectLabel(damage: TechniqueEffectSummary['damage'][number]): string {
  const type = damage.damage_type ?? 'untyped';
  const source = damage.uses_equipped_weapon ? 'weapon' : `${damage.base_damage}`;
  return `${type} (${source})`;
}

export function TechniqueEffectSummaryDisplay({
  summary,
  variant = 'full',
  className,
}: TechniqueEffectSummaryDisplayProps) {
  if (summary.is_underspecified) {
    return (
      <p
        className={cn('text-xs italic text-muted-foreground', className)}
        data-testid="technique-effect-summary-underspecified"
      >
        Effects not yet catalogued.
      </p>
    );
  }

  if (variant === 'compact') {
    return (
      <p
        className={cn('flex items-center gap-1 truncate text-xs text-muted-foreground', className)}
        data-testid="technique-effect-summary-compact"
      >
        {summary.hostile && (
          <AlertTriangle
            aria-label="Hostile: may trigger combat"
            className="h-3 w-3 shrink-0 text-amber-400"
          />
        )}
        <span className="truncate">{summary.summary}</span>
      </p>
    );
  }

  const hasDetail =
    summary.applies.length > 0 ||
    summary.removes.length > 0 ||
    summary.damage.length > 0 ||
    summary.grants.length > 0;

  return (
    <div className={cn('space-y-1.5', className)} data-testid="technique-effect-summary-full">
      <p className="flex items-start gap-1 text-sm text-muted-foreground">
        {summary.hostile && (
          <AlertTriangle
            aria-label="Hostile: may trigger combat"
            className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-400"
          />
        )}
        <span>{summary.summary}</span>
      </p>

      {hasDetail && (
        <div className="flex flex-wrap gap-1">
          {summary.applies.map((effect) => (
            <Badge key={`applies-${effect.name}`} variant="secondary" title={effect.description}>
              +{effect.name}
            </Badge>
          ))}
          {summary.removes.map((effect) => (
            <Badge key={`removes-${effect.name}`} variant="outline" title={effect.description}>
              −{effect.name}
            </Badge>
          ))}
          {summary.damage.map((damage, i) => (
            <Badge key={`damage-${i}`} variant="destructive">
              {damageEffectLabel(damage)}
            </Badge>
          ))}
          {summary.grants.map((grant) => (
            <Badge key={`grants-${grant.name}`} variant="default" title={grant.description}>
              {grant.name}
            </Badge>
          ))}
        </div>
      )}
    </div>
  );
}

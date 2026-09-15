/**
 * DistinctionLinkChips, toggleable badge chips linking a set of distinctions
 * to something (#2427, extracted from `GlimpseFlow` in #3675).
 *
 * CG no longer links distinctions this way (distinctions are offered by
 * chapter now, rendered through `GlimpseFlowProps.renderOffers`); this
 * component's sole remaining mount is `GlimpseEditorDialog`, the post-CG
 * "finish your Glimpse" sheet editor, which still links/unlinks a
 * character's *existing* CharacterDistinction rows to the glimpse (a
 * different feature from CG's offer-based picks).
 */

import { Badge } from '@/components/ui/badge';
import { Label } from '@/components/ui/label';
import { Check } from 'lucide-react';

export interface DistinctionLinkOption {
  id: number;
  name: string;
}

interface DistinctionLinkChipsProps {
  distinctions: DistinctionLinkOption[];
  linkedIds: Set<number>;
  onToggle: (distinctionId: number) => void;
  label: string;
}

export function DistinctionLinkChips({
  distinctions,
  linkedIds,
  onToggle,
  label,
}: DistinctionLinkChipsProps) {
  return (
    <div className="space-y-2">
      <Label>{label}</Label>
      {distinctions.length > 0 ? (
        <div className="flex flex-wrap gap-2">
          {distinctions.map((distinction) => {
            const isLinked = linkedIds.has(distinction.id);
            return (
              <Badge
                key={distinction.id}
                variant={isLinked ? 'default' : 'outline'}
                className="cursor-pointer select-none"
                onClick={() => onToggle(distinction.id)}
              >
                {isLinked && <Check className="mr-1 h-3 w-3" />}
                {distinction.name}
              </Badge>
            );
          })}
        </div>
      ) : (
        <p className="text-xs text-muted-foreground">No distinctions to link yet.</p>
      )}
    </div>
  );
}

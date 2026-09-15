/**
 * The questions a Family Template asks and the facts it stamps (#2079, #3648).
 * Shared by the noble house claim and the name path. Pure presentation.
 */

import { Label } from '@/components/ui/label';
import { cn } from '@/lib/utils';
import type { FamilyTemplate } from '../../types';

interface Props {
  template: Pick<FamilyTemplate, 'aspect_definitions' | 'features'>;
  picks: Record<number, number[]>;
  onToggle: (definitionId: number, optionId: number, maxPicks: number) => void;
  featuresHeading?: string;
}

export function FamilyTemplateForm({
  template,
  picks,
  onToggle,
  featuresHeading = 'A family like yours',
}: Props) {
  return (
    <div className="space-y-4">
      {template.features.length > 0 && (
        <div className="space-y-1 rounded-md border bg-muted/30 p-2">
          <Label className="text-xs font-medium text-muted-foreground">{featuresHeading}</Label>
          {template.features.map((feature) => (
            <p key={feature.id} className="text-xs">
              <span className="font-medium">{feature.name}</span>: {feature.description}
            </p>
          ))}
        </div>
      )}
      {template.aspect_definitions.map((definition) => {
        const picked = picks[definition.id] ?? [];
        const maxPicks = definition.max_picks ?? 1;
        return (
          <div key={definition.id} className="space-y-1">
            <Label className="text-sm font-medium">
              {definition.name}
              {maxPicks > 1 && (
                <span className="ml-1 text-xs text-muted-foreground">
                  ({picked.length}/{maxPicks})
                </span>
              )}
            </Label>
            <p className="text-xs text-muted-foreground">{definition.prompt}</p>
            <div className="grid gap-1 sm:grid-cols-2">
              {definition.options.map((option) => (
                <button
                  key={option.id}
                  type="button"
                  aria-pressed={picked.includes(option.id)}
                  onClick={() => onToggle(definition.id, option.id, maxPicks)}
                  className={cn(
                    'rounded-md border p-2 text-left text-xs transition-colors',
                    picked.includes(option.id)
                      ? 'border-primary bg-primary/10'
                      : 'hover:bg-muted/50'
                  )}
                >
                  <span className="font-medium">{option.name}</span>
                  {option.description && (
                    <span className="block text-muted-foreground">{option.description}</span>
                  )}
                </button>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}

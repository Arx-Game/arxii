/** Facts inherited from the claimed family's Family Template (#3648). */

import { Label } from '@/components/ui/label';
import type { Family } from '../../types';

interface Props {
  family: Family | undefined;
}

export function InheritedFactsPanel({ family }: Props) {
  const inherited = family?.inherited;
  if (!inherited) return null;
  const { aspects, features, liege_name } = inherited;
  if (aspects.length === 0 && features.length === 0 && !liege_name) return null;
  return (
    <div className="space-y-2 rounded-md border bg-muted/30 p-3 text-sm">
      {liege_name && <p className="text-xs text-muted-foreground">Sworn to {liege_name}</p>}
      {aspects.map((aspect) => (
        <div key={`${aspect.definition}:${aspect.option}`}>
          <p>
            <b>{aspect.definition}</b>: {aspect.option}
          </p>
          {aspect.description && (
            <p className="text-xs text-muted-foreground">{aspect.description}</p>
          )}
        </div>
      ))}
      {features.length > 0 && (
        <div className="space-y-1 rounded-md border bg-muted/30 p-2">
          <Label className="text-xs font-medium text-muted-foreground">A family like yours</Label>
          {features.map((feature) => (
            <p key={feature.slug} className="text-xs">
              <span className="font-medium">{feature.name}</span>: {feature.description}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}

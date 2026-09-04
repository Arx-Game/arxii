/**
 * Upbringing picker (#3617).
 *
 * One card per OriginTemplate ("Upbringing" in CG copy) offered for the
 * draft's chosen Beginning. Selecting a card PATCHes selected_origin_template_id.
 */

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import type { OriginTemplate } from '../../types';

interface Props {
  templates: OriginTemplate[];
  selectedId: number | null;
  onSelect: (template: OriginTemplate) => void;
}

function costLabel(cost: number): string {
  if (cost === 0) return 'Free';
  return cost > 0 ? `${cost} points` : `Refunds ${-cost} points`;
}

export function UpbringingPicker({ templates, selectedId, onSelect }: Props) {
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      {templates.map((template) => (
        <Card
          key={template.id}
          role="button"
          tabIndex={0}
          aria-pressed={template.id === selectedId}
          className={cn(
            'cursor-pointer transition-all',
            template.id === selectedId
              ? 'ring-2 ring-primary'
              : 'hover:ring-1 hover:ring-primary/50'
          )}
          onClick={() => onSelect(template)}
          onKeyDown={(e) => e.key === 'Enter' && onSelect(template)}
        >
          <CardHeader>
            <div className="flex items-center justify-between gap-2">
              <CardTitle className="text-base">{template.name}</CardTitle>
              <Badge variant={template.cg_point_cost > 0 ? 'default' : 'secondary'}>
                {costLabel(template.cg_point_cost)}
              </Badge>
            </div>
          </CardHeader>
          <CardContent>
            <CardDescription className="whitespace-pre-wrap">
              {template.frame_narrative}
            </CardDescription>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

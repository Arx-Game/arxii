import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import type { OwnedDwelling } from '../types';
import { PolishCategoryList } from './PolishCategoryList';

interface Props {
  dwellings: OwnedDwelling[];
}

/**
 * Owned dwellings — per-building polish breakdown + condition label. One
 * sub-section per building this persona owns.
 *
 * `condition_label` is the qualitative condition-tier fiction (#1930) —
 * the only condition surface on this (any-viewer) payload. Arrears and
 * upkeep detail are owner-only and live on the building actions instead.
 */
export function OwnedDwellingsCard({ dwellings }: Props) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Owned Dwellings</CardTitle>
      </CardHeader>
      <CardContent>
        {dwellings.length === 0 ? (
          <p className="text-sm text-muted-foreground">This persona owns no buildings.</p>
        ) : (
          <ul className="space-y-4 text-sm">
            {dwellings.map((dwelling) => (
              <li key={dwelling.id} className="border-b pb-3 last:border-b-0">
                <div className="flex items-baseline justify-between gap-2">
                  <span className="font-semibold">{dwelling.name}</span>
                  <Badge variant="outline">{dwelling.condition_label}</Badge>
                </div>
                <PolishCategoryList rows={dwelling.polish_by_category} />
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { AlertTriangle, Moon } from 'lucide-react';
import type { OwnedDwelling } from '../types';

interface Props {
  dwellings: OwnedDwelling[];
}

function formatDate(iso: string | null): string {
  if (!iso) return '';
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  } catch {
    return iso;
  }
}

/**
 * Owned dwellings — per-building polish breakdown + upkeep state. One
 * sub-section per building this persona owns.
 *
 * - `upkeep_warning` (any instance with `consecutive_missed_upkeep > 0`)
 *   surfaces a destructive badge so the player notices before features
 *   start decaying further.
 * - `decayed_features_count > 0` shows the count alongside a
 *   restoration-needed hint.
 * - `dormant` flips the whole card to a muted state with the date the
 *   building went dormant.
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
              <li
                key={dwelling.id}
                className={`border-b pb-3 last:border-b-0 ${dwelling.dormant ? 'opacity-60' : ''}`}
              >
                <div className="flex items-baseline justify-between gap-2">
                  <span className="font-semibold">{dwelling.name}</span>
                  <div className="flex flex-wrap items-center gap-2">
                    {dwelling.dormant && (
                      <Badge variant="outline" className="gap-1">
                        <Moon className="h-3 w-3" />
                        Dormant
                        {dwelling.dormant_since
                          ? ` since ${formatDate(dwelling.dormant_since)}`
                          : ''}
                      </Badge>
                    )}
                    {dwelling.upkeep_warning && !dwelling.dormant && (
                      <Badge variant="destructive" className="gap-1">
                        <AlertTriangle className="h-3 w-3" />
                        Upkeep missed
                      </Badge>
                    )}
                    {dwelling.decayed_features_count > 0 && (
                      <Badge variant="secondary">{dwelling.decayed_features_count} decayed</Badge>
                    )}
                  </div>
                </div>
                {dwelling.polish_by_category.length === 0 ? (
                  <p className="mt-1 text-xs text-muted-foreground">No polish recorded yet.</p>
                ) : (
                  <ul className="mt-2 space-y-1 text-xs">
                    {dwelling.polish_by_category.map((row) => (
                      <li
                        key={row.category_id}
                        className="flex items-baseline justify-between gap-2"
                      >
                        <span>
                          {row.tier_label !== null && (
                            <span className="mr-1 font-medium">{row.tier_label}</span>
                          )}
                          <span className="text-muted-foreground">{row.category_name}</span>
                        </span>
                        <span className="font-mono text-foreground">
                          {row.value.toLocaleString()}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

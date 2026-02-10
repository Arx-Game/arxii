/**
 * ResonanceContextPanel Component
 *
 * Displays projected resonances from distinctions during character creation.
 * Shows resonance names, totals, and source breakdowns so players can see
 * how their distinction choices contribute to their magical resonances.
 */

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import type { ProjectedResonance } from '../../types';

interface ResonanceContextPanelProps {
  projectedResonances: ProjectedResonance[] | undefined;
  isLoading?: boolean;
}

export function ResonanceContextPanel({
  projectedResonances,
  isLoading,
}: ResonanceContextPanelProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">Your Resonances</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="space-y-2">
            <div className="h-4 w-full animate-pulse rounded bg-muted" />
            <div className="h-4 w-2/3 animate-pulse rounded bg-muted" />
          </div>
        ) : !projectedResonances || projectedResonances.length === 0 ? (
          <p className="text-sm text-muted-foreground">No resonances from distinctions</p>
        ) : (
          <div className="space-y-3">
            {projectedResonances.map((resonance) => (
              <div key={resonance.resonance_id}>
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium">{resonance.resonance_name}</span>
                  <span className="text-sm font-medium text-green-600">
                    {`+${resonance.total}`}
                  </span>
                </div>
                {resonance.sources.map((source, index) => (
                  <div key={index} className="text-xs text-muted-foreground">
                    {`${source.distinction_name} (+${source.value})`}
                  </div>
                ))}
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import type { FameBlock } from '../types';

interface Props {
  fame: FameBlock;
}

/**
 * Fame block — tier label, multiplier, current points, progress toward
 * next tier. ``next_tier`` is null when the persona is at World Famous
 * (top tier); we hide the progress bar in that case.
 */
export function FameCard({ fame }: Props) {
  const progress =
    fame.next_tier_threshold !== null && fame.next_tier_threshold > 0
      ? Math.min(100, Math.round((fame.points / fame.next_tier_threshold) * 100))
      : 100;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Fame</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex items-baseline justify-between">
          <span className="text-2xl font-semibold">{fame.tier_label}</span>
          <span className="text-sm text-muted-foreground">
            ×{fame.tier_multiplier.toFixed(2)} prestige
          </span>
        </div>
        <div className="text-sm">
          <span className="font-medium">{fame.points.toLocaleString()}</span> fame
          {fame.next_tier !== null && fame.next_tier_threshold !== null ? (
            <span className="text-muted-foreground">
              {' '}
              / {fame.next_tier_threshold.toLocaleString()} to next tier
            </span>
          ) : (
            <span className="text-muted-foreground"> (top tier)</span>
          )}
        </div>
        {fame.next_tier !== null && <Progress value={progress} className="h-2" />}
      </CardContent>
    </Card>
  );
}

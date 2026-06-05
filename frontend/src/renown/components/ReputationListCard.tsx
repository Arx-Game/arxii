import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import type { SocietyReputationEntry } from '../types';

interface Props {
  reputation: SocietyReputationEntry[];
}

const TIER_VARIANT: Record<string, 'default' | 'secondary' | 'destructive' | 'outline'> = {
  reviled: 'destructive',
  despised: 'destructive',
  disliked: 'destructive',
  disfavored: 'secondary',
  unknown: 'outline',
  favored: 'secondary',
  liked: 'default',
  honored: 'default',
  revered: 'default',
};

function formatTier(tier: string): string {
  return tier.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

/**
 * Per-society reputation list. Named tier labels only — the raw numeric
 * value is intentionally never exposed to the client (#676 spec).
 */
export function ReputationListCard({ reputation }: Props) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Reputation</CardTitle>
      </CardHeader>
      <CardContent>
        {reputation.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No societies have a recorded opinion of this persona yet.
          </p>
        ) : (
          <ul className="space-y-2 text-sm">
            {reputation.map((entry) => (
              <li key={entry.society_id} className="flex items-center justify-between">
                <span className="font-medium">{entry.society_name}</span>
                <Badge variant={TIER_VARIANT[entry.tier] ?? 'outline'}>
                  {formatTier(entry.tier)}
                </Badge>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

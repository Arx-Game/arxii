/**
 * PendingClaimRow — single row for a pending AGM claim in GMQueuePage.
 *
 * Read-only for Wave 5. Action UIs (approve / reject) come in Wave 6.
 */

import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { formatRelativeTime } from '@/lib/relativeTime';
import type { GMQueuePendingClaim } from '../types';

interface PendingClaimRowProps {
  claim: GMQueuePendingClaim;
}

const EXCERPT_LENGTH = 120;

function excerpt(text: string): string {
  if (text.length <= EXCERPT_LENGTH) return text;
  return text.slice(0, EXCERPT_LENGTH).trimEnd() + '…';
}

export function PendingClaimRow({ claim }: PendingClaimRowProps) {
  return (
    <Card data-testid="pending-claim-row">
      <CardContent className="py-4">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-base font-semibold">{claim.story_title}</span>
          <Badge className="border-transparent bg-amber-600 text-white">PENDING</Badge>
        </div>

        {claim.beat_internal_description && (
          <p className="mt-1 text-sm text-muted-foreground">
            {excerpt(claim.beat_internal_description)}
          </p>
        )}

        <div className="mt-2 flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
          <span>AGM #{claim.assistant_gm_id}</span>
          <span>Requested {formatRelativeTime(claim.requested_at)}</span>
        </div>
      </CardContent>
    </Card>
  );
}

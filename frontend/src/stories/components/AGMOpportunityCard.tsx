/**
 * AGMOpportunityCard — a single AGM-eligible beat row on the Opportunities page.
 *
 * Shows beat context (description, story/episode hierarchy, scope badge),
 * an indicator if the current user already has an active claim, and the
 * RequestClaimDialog trigger.
 */

import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import { RequestClaimDialog } from './RequestClaimDialog';
import type { AssistantGMClaim, Beat } from '../types';

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface AGMOpportunityCardProps {
  beat: Beat;
  /** Claims already made by the current user on this beat (may be empty). */
  myClaimsOnBeat: AssistantGMClaim[];
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const EXCERPT_LENGTH = 200;

function excerpt(text: string): string {
  if (text.length <= EXCERPT_LENGTH) return text;
  return text.slice(0, EXCERPT_LENGTH).trimEnd() + '…';
}

/** Active claim statuses — user should not request again while one is active. */
const ACTIVE_STATUSES = new Set(['requested', 'approved']);

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function AGMOpportunityCard({ beat, myClaimsOnBeat }: AGMOpportunityCardProps) {
  const activeClaim = myClaimsOnBeat.find((c) => ACTIVE_STATUSES.has(c.status ?? ''));
  const hasActiveClaim = activeClaim !== undefined;

  const beatDescription =
    beat.internal_description && beat.internal_description.trim().length > 0
      ? beat.internal_description
      : (beat.player_hint ?? '(no description)');

  return (
    <Card data-testid="agm-opportunity-card">
      <CardContent className="py-4">
        {/* Header: story + scope */}
        <div className="flex flex-wrap items-center gap-2">
          {beat.story_title && <span className="text-base font-semibold">{beat.story_title}</span>}
          {hasActiveClaim && (
            <Badge className="border-transparent bg-amber-600 text-white">Already claimed</Badge>
          )}
          {beat.agm_eligible && (
            <Badge className="border-transparent bg-emerald-600 text-white">AGM eligible</Badge>
          )}
        </div>

        {/* Episode / chapter breadcrumb */}
        {(beat.chapter_title || beat.episode_title) && (
          <p className="mt-1 text-xs text-muted-foreground">
            {[beat.chapter_title, beat.episode_title].filter(Boolean).join(' › ')}
          </p>
        )}

        {/* Beat description */}
        <p className="mt-2 text-sm text-foreground">{excerpt(beatDescription)}</p>

        {/* Deadline if set */}
        {beat.deadline && (
          <p className="mt-1 text-xs text-muted-foreground">
            Deadline: {new Date(beat.deadline).toLocaleDateString()}
          </p>
        )}

        {/* Action */}
        <div className="mt-3 flex items-center gap-2">
          {hasActiveClaim ? (
            <p className="text-xs text-muted-foreground">
              You have a <span className="font-medium capitalize">{activeClaim?.status}</span> claim
              on this beat.
            </p>
          ) : (
            <RequestClaimDialog beat={beat} />
          )}
        </div>
      </CardContent>
    </Card>
  );
}

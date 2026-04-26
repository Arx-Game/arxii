/**
 * Beat outcome pill badge.
 * SUCCESS=green, FAILURE=red, EXPIRED=gray, UNSATISFIED=neutral, PENDING_GM_REVIEW=amber.
 */

import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import type { BeatOutcome } from '../types';

const OUTCOME_LABELS: Record<BeatOutcome, string> = {
  unsatisfied: 'Unsatisfied',
  success: 'Success',
  failure: 'Failure',
  expired: 'Expired',
  pending_gm_review: 'Pending Review',
};

const OUTCOME_CLASSES: Record<BeatOutcome, string> = {
  unsatisfied: 'bg-secondary text-secondary-foreground border-transparent',
  success: 'bg-green-600 text-white border-transparent',
  failure: 'bg-red-600 text-white border-transparent',
  expired: 'bg-gray-500 text-white border-transparent',
  pending_gm_review: 'bg-amber-600 text-white border-transparent',
};

interface BeatOutcomeBadgeProps {
  outcome: BeatOutcome;
  className?: string;
}

export function BeatOutcomeBadge({ outcome, className }: BeatOutcomeBadgeProps) {
  return (
    <Badge className={cn(OUTCOME_CLASSES[outcome], className)}>{OUTCOME_LABELS[outcome]}</Badge>
  );
}

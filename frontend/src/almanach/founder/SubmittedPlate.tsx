/**
 * SubmittedPlate (#3983 Plan B Task 6, plate F-VI's `.night`) — the full-
 * bleed "night" moment a filed house claim shows in place of the whole
 * chassis (no `.bar` crumb, no `.almanac` grid — the plate's own `.night`
 * sits as a sibling of the form, not inside it). Two call sites share it:
 * `FounderRecord`'s own submit success (an immediate, locally-known
 * `'pending'` status, before the invalidated query round-trips) and
 * `FounderAlmanach`'s steady-state read of `useHouseClaim` on any later
 * visit (pending/approved/rejected, with staff's `review_note` once one
 * exists).
 */
import type { HouseClaimStatus } from '@/character-creation/api';

/** `HouseClaimStatus.status` is optional on the wire (a pre-review row
 * might not carry one) — this component always has a real status to show
 * (the caller defaults a missing one to `'pending'`), so it narrows to the
 * non-optional enum rather than re-widening to `undefined` here too. */
export type SubmittedStatus = NonNullable<HouseClaimStatus['status']>;

export interface SubmittedPlateProps {
  houseName: string;
  status: SubmittedStatus;
  reviewNote?: string;
}

const STATUS_TEXT: Record<SubmittedStatus, string> = {
  pending: 'pending review',
  approved: 'approved',
  rejected: 'not approved',
};

export function SubmittedPlate({ houseName, status, reviewNote }: SubmittedPlateProps) {
  return (
    <div className="night">
      <h3>Submitted</h3>
      <p>
        House {houseName} · {STATUS_TEXT[status]}
      </p>
      {reviewNote != null && reviewNote !== '' && <p>{reviewNote}</p>}
    </div>
  );
}

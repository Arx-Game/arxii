/**
 * ClearanceInbox — custody clearance inbox, mounted on GMQueuePage (#2001 Task 8).
 *
 * Mount point rationale (brief asks to read StoryDetailPage/GMQueuePage/
 * TableDetailPage and pick the least-invasive existing GM surface): GMQueuePage
 * is the canonical "GM's current work queue" — session requests, AGM claims,
 * episodes ready to run all live there already. Custody clearance decisions
 * are structurally GM/staff-only too: `IsClearanceCustodianGM` requires an
 * exact table-GM match with *no* staff bypass (grant/deny), so a bare story
 * owner without a GM profile can view but never act on incoming requests —
 * mounting this here (rather than e.g. StoryDetailPage, which would be
 * reachable by non-GM viewers) matches that actionability. It is mounted as
 * its own `<ErrorBoundary>` sibling of `GMQueueInner`, NOT nested inside it —
 * `GMQueueInner` early-returns a "not a GM" page on the *aggregate*
 * `gm-queue` endpoint's 403 (`IsGMProfile`), but staff resolving escalations
 * may have no GMProfile at all, so this inbox must render independent of
 * that gate.
 *
 * GET /api/custody-clearances/ has no "am I the requester vs. the custodian"
 * filter — the queryset already returns rows for both roles combined
 * (`story__owners=user | requested_by=gm_profile | story__primary_table__gm=
 * gm_profile`). Splitting client-side: any clearance whose `protected_subject`
 * appears in the caller's own `/api/protected-subjects/` list (same
 * owner/lead-GM scope) is "incoming" (I may be its custodian); everything
 * else must be reaching this list via `requested_by=gm_profile`, i.e. "outgoing"
 * (my own request) — no need to know my own GMProfile id to tell them apart.
 *
 * For a plain staff account (no GMProfile, no owned story), `protected-subjects`
 * returns literally everything unfiltered (`if user.is_staff: return qs`), which
 * would misleadingly bucket every clearance in the system as "incoming" with a
 * false sense of custodian authority grant/deny doesn't actually have (no staff
 * bypass there). So staff skip Incoming/Outgoing and see only the dedicated
 * Staff Escalation Queue below (a known simplification — a staff account that
 * *also* runs their own GM table won't see their own incoming/outgoing rows
 * here; noted rather than worked around, since resolving escalations is the
 * staff-relevant action this inbox exists to support).
 *
 * Revoke posture ("hide rather than probe", per brief): `IsClearanceCustodianOrStaff`
 * allows the custodian GM OR staff — never a bare owner without GM identity, and
 * never the requester. Outgoing rows are (by the split above) never ones the
 * viewer is custodian for, so Revoke only shows there when the viewer is staff.
 * Incoming rows ARE the viewer's own custodianship, so Revoke shows unconditionally
 * there (grant/deny is additionally staff-excluded, since IsClearanceCustodianGM has
 * no staff bypass at all).
 */

import { useMemo } from 'react';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { formatRelativeTime } from '@/lib/relativeTime';
import { useAccount } from '@/store/hooks';
import { useCustodyClearances, useProtectedSubjects } from '../queries';
import type { CustodyClearance } from '../types';
import { ClearanceStatusBadge } from './ClearanceStatusBadge';
import { DenyClearanceDialog } from './DenyClearanceDialog';
import { EscalateClearanceButton } from './EscalateClearanceButton';
import { GrantClearanceDialog } from './GrantClearanceDialog';
import { RequestClearanceDialog } from './RequestClearanceDialog';
import { ResolveClearanceDialog } from './ResolveClearanceDialog';
import { RevokeClearanceButton } from './RevokeClearanceButton';

// Mirrors CUSTODY_ESCALATION_STALE_DAYS in world/stories/constants.py — no API
// surface exposes this threshold, so it's hand-mirrored (same pattern as other
// hand-authored constants in this module's types.ts).
const CUSTODY_ESCALATION_STALE_DAYS = 7;

function isStalePending(clearance: CustodyClearance): boolean {
  if (clearance.status !== 'pending') return false;
  const ageMs = Date.now() - new Date(clearance.created_at).getTime();
  return ageMs >= CUSTODY_ESCALATION_STALE_DAYS * 24 * 60 * 60 * 1000;
}

function SectionSkeleton() {
  return (
    <div className="space-y-2">
      {[0, 1].map((i) => (
        <Skeleton key={i} className="h-20 w-full" />
      ))}
    </div>
  );
}

function ClearanceRow({
  clearance,
  isIncoming,
  isStaff,
}: {
  clearance: CustodyClearance;
  isIncoming: boolean;
  isStaff: boolean;
}) {
  const canActAsCustodian = isIncoming && !isStaff; // grant/deny — no staff bypass
  const canRevoke =
    clearance.status === 'granted' && clearance.revoked_at == null && (isIncoming || isStaff);
  const canEscalate = !isIncoming && (clearance.status === 'denied' || isStalePending(clearance));

  return (
    <Card data-testid="clearance-row">
      <CardContent className="space-y-2 py-4">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-medium">
            Protected subject #{clearance.protected_subject}
          </span>
          <ClearanceStatusBadge status={clearance.status} />
          <Badge variant="outline">{clearance.scope}</Badge>
        </div>
        {clearance.message && <p className="text-sm text-muted-foreground">{clearance.message}</p>}
        {clearance.response_note && (
          <p className="text-sm text-muted-foreground">
            <span className="font-medium">Response: </span>
            {clearance.response_note}
          </p>
        )}
        <p className="text-xs text-muted-foreground">
          Requested {formatRelativeTime(clearance.created_at)}
        </p>
        <div className="flex flex-wrap items-center gap-2 pt-1">
          {canActAsCustodian && clearance.status === 'pending' && (
            <>
              <GrantClearanceDialog clearanceId={clearance.id} />
              <DenyClearanceDialog clearanceId={clearance.id} />
            </>
          )}
          {canEscalate && <EscalateClearanceButton clearanceId={clearance.id} />}
          {canRevoke && <RevokeClearanceButton clearanceId={clearance.id} />}
        </div>
      </CardContent>
    </Card>
  );
}

function NonStaffInbox() {
  const { data: subjectsData, isLoading: subjectsLoading } = useProtectedSubjects({
    page_size: 200,
  });
  const { data: clearancesData, isLoading: clearancesLoading } = useCustodyClearances({
    page_size: 200,
  });

  const myProtectedSubjectIds = useMemo(
    () => new Set((subjectsData?.results ?? []).map((s) => s.id)),
    [subjectsData]
  );

  const clearances = clearancesData?.results ?? [];
  const incoming = clearances.filter((c) => myProtectedSubjectIds.has(c.protected_subject));
  const outgoing = clearances.filter((c) => !myProtectedSubjectIds.has(c.protected_subject));

  const isLoading = subjectsLoading || clearancesLoading;

  return (
    <>
      <section data-testid="incoming-clearances-section">
        <h3 className="text-base font-semibold">Incoming ({incoming.length})</h3>
        <p className="text-sm text-muted-foreground">
          Requests from other GMs to act on your stories&apos; protected subjects.
        </p>
        <div className="mt-3 space-y-3">
          {isLoading ? (
            <SectionSkeleton />
          ) : incoming.length === 0 ? (
            <p className="py-2 text-sm text-muted-foreground">No incoming requests.</p>
          ) : (
            incoming.map((c) => (
              <ClearanceRow key={c.id} clearance={c} isIncoming isStaff={false} />
            ))
          )}
        </div>
      </section>

      <section className="mt-8" data-testid="outgoing-clearances-section">
        <h3 className="text-base font-semibold">Outgoing ({outgoing.length})</h3>
        <p className="text-sm text-muted-foreground">
          Your own requests on other stories&apos; subjects.
        </p>
        <div className="mt-3 space-y-3">
          {isLoading ? (
            <SectionSkeleton />
          ) : outgoing.length === 0 ? (
            <p className="py-2 text-sm text-muted-foreground">No outgoing requests.</p>
          ) : (
            outgoing.map((c) => (
              <ClearanceRow key={c.id} clearance={c} isIncoming={false} isStaff={false} />
            ))
          )}
        </div>
      </section>
    </>
  );
}

function StaffEscalationQueue() {
  const { data, isLoading } = useCustodyClearances({ status: 'escalated', page_size: 200 });
  const escalated = data?.results ?? [];

  return (
    <section data-testid="staff-escalation-section">
      <h3 className="text-base font-semibold">Staff Escalation Queue ({escalated.length})</h3>
      <p className="text-sm text-muted-foreground">Clearances escalated for a staff tiebreak.</p>
      <div className="mt-3 space-y-3">
        {isLoading ? (
          <SectionSkeleton />
        ) : escalated.length === 0 ? (
          <p className="py-2 text-sm text-muted-foreground">No escalated clearances.</p>
        ) : (
          escalated.map((c) => (
            <Card key={c.id} data-testid="clearance-row">
              <CardContent className="space-y-2 py-4">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-medium">
                    Protected subject #{c.protected_subject}
                  </span>
                  <ClearanceStatusBadge status={c.status} />
                  <Badge variant="outline">{c.scope}</Badge>
                </div>
                {c.message && <p className="text-sm text-muted-foreground">{c.message}</p>}
                <p className="text-xs text-muted-foreground">
                  Requested {formatRelativeTime(c.created_at)}
                </p>
                <div className="pt-1">
                  <ResolveClearanceDialog clearanceId={c.id} />
                </div>
              </CardContent>
            </Card>
          ))
        )}
      </div>
    </section>
  );
}

export function ClearanceInbox() {
  const account = useAccount();
  const isStaff = account?.is_staff ?? false;

  return (
    <div data-testid="clearance-inbox">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-lg font-semibold text-foreground">Custody Clearances</h2>
        <RequestClearanceDialog />
      </div>
      {isStaff ? <StaffEscalationQueue /> : <NonStaffInbox />}
    </div>
  );
}

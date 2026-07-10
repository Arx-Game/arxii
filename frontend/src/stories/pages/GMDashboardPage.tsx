/**
 * GMDashboardPage — the GM's story-shaped dashboard (#2004).
 *
 * Shows the GM's tables, upcoming sessions, stories needing attention,
 * pending AGM claims, pending story offers, and evidence summary from
 * GET /api/gm/dashboard/.
 *
 * Permission gating: the endpoint returns 403 for non-GMs. We use a local
 * query with throwOnError: false so we can render a friendly "not a GM" page
 * rather than blowing the error boundary.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Button } from '@/components/ui/button';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { Skeleton } from '@/components/ui/skeleton';
import { apiFetch } from '@/evennia_replacements/api';
import { useAccount } from '@/store/hooks';

// ---------------------------------------------------------------------------
// Types (manually authored — spectacular can't introspect this APIView)
// ---------------------------------------------------------------------------

interface GMDashboardTable {
  id: number;
  name: string;
  membership_count: number;
}

interface GMDashboardOffer {
  id: number;
  story__title: string;
  created_at: string;
}

interface GMDashboardEvidence {
  level: string;
  stories_running: number;
  beats_completed_by_risk: Record<string, number>;
  last_active_at: string | null;
}

/** One open (PENDING) GroupStoryRequest — the broadcast GM-recruitment queue (#2119). */
interface GMDashboardOpenGroupRequest {
  request_id: number;
  covenant_id: number;
  covenant_name: string;
  message: string;
  created_at: string;
}

interface GMDashboardResponse {
  episodes_ready_to_run: unknown[];
  pending_agm_claims: unknown[];
  assigned_session_requests: unknown[];
  waiting_for_gm: unknown[];
  open_group_requests: GMDashboardOpenGroupRequest[];
  my_tables: GMDashboardTable[];
  pending_story_offers: GMDashboardOffer[];
  evidence_summary: GMDashboardEvidence;
}

async function getGMDashboard(): Promise<GMDashboardResponse> {
  const res = await apiFetch('/api/gm/dashboard/');
  if (!res.ok) {
    const err = new Error('Failed to load GM dashboard') as Error & { status?: number };
    err.status = res.status;
    throw err;
  }
  return res.json() as Promise<GMDashboardResponse>;
}

/**
 * Dispatch ClaimGroupStoryRequestAction as the actor's own character
 * (characterId is the ObjectDB pk — doubles as the character_sheet pk, since
 * CharacterSheet.character is a primary_key=True OneToOneField). Mirrors the
 * generic-dispatch pattern in @/game/api/roomEditor.ts (#2119, Decision 8:
 * the generic action-dispatch endpoint, never a bespoke @action).
 */
async function claimGroupStoryRequest(characterId: number, requestId: number): Promise<string> {
  const res = await apiFetch(`/api/actions/characters/${characterId}/dispatch/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      ref: { backend: 'registry', registry_key: 'claim_group_story_request' },
      kwargs: { request_id: requestId },
    }),
  });
  let detail: string | undefined;
  try {
    const data = (await res.json()) as { detail?: string; message?: string | null };
    detail = data.detail ?? data.message ?? undefined;
  } catch {
    detail = undefined;
  }
  if (!res.ok) throw new Error(detail ?? 'Failed to claim the request.');
  return detail ?? 'Request claimed.';
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function GMDashboardPage() {
  return (
    <ErrorBoundary>
      <GMDashboardContent />
    </ErrorBoundary>
  );
}

function GMDashboardContent() {
  const account = useAccount();
  const queryClient = useQueryClient();
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['gm-dashboard'],
    queryFn: getGMDashboard,
    throwOnError: false,
  });

  // The GM's active character's ObjectDB pk — doubles as the character_sheet
  // pk (see claimGroupStoryRequest doc comment). Needed to dispatch the claim
  // action as this GM's own character.
  const activeCharacter =
    account?.available_characters?.find((c) => c.currently_puppeted_in_session) ?? null;
  const actorCharacterId = activeCharacter?.id ?? null;

  const claimMutation = useMutation({
    mutationFn: (requestId: number) => {
      if (actorCharacterId === null) {
        return Promise.reject(new Error('Puppet a character to claim a request.'));
      }
      return claimGroupStoryRequest(actorCharacterId, requestId);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['gm-dashboard'] }).catch(() => {});
    },
  });

  if (isLoading) {
    return <Skeleton className="h-96 w-full" />;
  }

  if (isError) {
    const status = (error as Error & { status?: number }).status;
    if (status === 403) {
      return (
        <div className="p-8 text-center text-muted-foreground">
          You must be a GM to view this page.
        </div>
      );
    }
    return (
      <div className="p-8 text-center text-destructive">
        Failed to load dashboard: {error?.message}
      </div>
    );
  }

  if (!data) return null;

  return (
    <div className="mx-auto max-w-4xl space-y-6 p-6">
      <h1 className="text-2xl font-bold">GM Dashboard</h1>

      {/* Evidence summary */}
      <section className="rounded-lg border p-4">
        <h2 className="mb-2 text-lg font-semibold">Your GM Profile</h2>
        <dl className="grid grid-cols-2 gap-2 text-sm">
          <dt className="text-muted-foreground">Level</dt>
          <dd>{data.evidence_summary.level}</dd>
          <dt className="text-muted-foreground">Stories running</dt>
          <dd>{data.evidence_summary.stories_running}</dd>
          <dt className="text-muted-foreground">Last active</dt>
          <dd>
            {data.evidence_summary.last_active_at
              ? new Date(data.evidence_summary.last_active_at).toLocaleDateString()
              : 'Never'}
          </dd>
        </dl>
      </section>

      {/* My tables */}
      <section className="rounded-lg border p-4">
        <h2 className="mb-2 text-lg font-semibold">My Tables ({data.my_tables.length})</h2>
        {data.my_tables.length === 0 ? (
          <p className="text-sm text-muted-foreground">No active tables.</p>
        ) : (
          <ul className="space-y-1 text-sm">
            {data.my_tables.map((table) => (
              <li key={table.id}>
                <span className="font-medium">{table.name}</span> — {table.membership_count}{' '}
                member(s)
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* Attention counts */}
      <section className="grid grid-cols-2 gap-4">
        <div className="rounded-lg border p-4">
          <p className="text-sm text-muted-foreground">Episodes ready to run</p>
          <p className="text-2xl font-bold">{data.episodes_ready_to_run.length}</p>
        </div>
        <div className="rounded-lg border p-4">
          <p className="text-sm text-muted-foreground">Pending AGM claims</p>
          <p className="text-2xl font-bold">{data.pending_agm_claims.length}</p>
        </div>
        <div className="rounded-lg border p-4">
          <p className="text-sm text-muted-foreground">Assigned sessions</p>
          <p className="text-2xl font-bold">{data.assigned_session_requests.length}</p>
        </div>
        <div className="rounded-lg border p-4">
          <p className="text-sm text-muted-foreground">Stories waiting on you</p>
          <p className="text-2xl font-bold">{data.waiting_for_gm.length}</p>
        </div>
      </section>

      {/* Pending story offers */}
      <section className="rounded-lg border p-4">
        <h2 className="mb-2 text-lg font-semibold">
          Pending Story Offers ({data.pending_story_offers.length})
        </h2>
        {data.pending_story_offers.length === 0 ? (
          <p className="text-sm text-muted-foreground">No pending offers.</p>
        ) : (
          <ul className="space-y-1 text-sm">
            {data.pending_story_offers.map((offer) => (
              <li key={offer.id}>
                <span className="font-medium">{offer.story__title}</span> —{' '}
                {new Date(offer.created_at).toLocaleDateString()}
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* Open group requests (#2119) — the broadcast covenant-GM recruitment queue */}
      <section className="rounded-lg border p-4">
        <h2 className="mb-2 text-lg font-semibold">
          Open Group Requests ({data.open_group_requests.length})
        </h2>
        {data.open_group_requests.length === 0 ? (
          <p className="text-sm text-muted-foreground">No covenants are recruiting right now.</p>
        ) : (
          <ul className="space-y-2 text-sm">
            {data.open_group_requests.map((request) => (
              <li
                key={request.request_id}
                className="flex items-center justify-between gap-3 rounded-md border px-3 py-2"
              >
                <div className="min-w-0">
                  <span className="font-medium">{request.covenant_name}</span>
                  {request.message && (
                    <p className="truncate text-xs text-muted-foreground">{request.message}</p>
                  )}
                </div>
                <Button
                  size="sm"
                  onClick={() => claimMutation.mutate(request.request_id)}
                  disabled={claimMutation.isPending || actorCharacterId === null}
                  data-testid="claim-group-request-button"
                >
                  {claimMutation.isPending && claimMutation.variables === request.request_id
                    ? 'Claiming…'
                    : 'Claim'}
                </Button>
              </li>
            ))}
          </ul>
        )}
        {claimMutation.isError && (
          <p className="mt-2 text-sm text-destructive">{(claimMutation.error as Error).message}</p>
        )}
      </section>
    </div>
  );
}

/**
 * GMDashboardPage — the GM's story-shaped dashboard (#2004).
 *
 * Opens on the "Waiting on you" strip (#4188, `WaitingOnYouStrip` over
 * GET /api/gm/attention/: offers, invites, requests, claims, sessions, each
 * row a door), then the GM's profile summary, tables, Story NPCs with the
 * new-NPC form (#3426, #4418 `NpcForm`), the remaining stat tiles and the open group requests, from
 * GET /api/gm/dashboard/ plus GET /api/roster/entries/mine/.
 *
 * Permission gating: the endpoint returns 403 for non-GMs. We use a local
 * query with throwOnError: false so we can render a friendly "not a GM" page
 * rather than blowing the error boundary.
 */

import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useSearchParams } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { Skeleton } from '@/components/ui/skeleton';
import { apiFetch } from '@/evennia_replacements/api';
import { parseDispatchBody } from '@/lib/errors';
import { gmKeys, useGMAttention } from '@/gm/queries';
import { NpcForm } from '@/gm/npcs/NpcForm';
import { NpcOwnerPanel } from '@/gm/npcs/NpcOwnerPanel';
import { useMyRosterEntriesQuery } from '@/roster/queries';
import { useAccount } from '@/store/hooks';
import { GMPromptFilterCard } from '../components/GMPromptFilterCard';
import { WaitingOnYouStrip } from '../components/WaitingOnYouStrip';

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
  /** Pending RosterApplications at this GM's tables (#3268). Reviewed from the per-table Recruitment tab. */
  pending_applications: number;
  /** This GM's unclaimed, unexpired roster invites (#3268). Managed from the per-table Recruitment tab. */
  open_invites: number;
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
 *
 * `DispatchActionView` resolves HTTP 200 even for a business-rule rejection
 * (e.g. someone else already claimed it) — `success === false` (not `res.ok`
 * alone) is the signal the claim was refused (#3155).
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
  const { success, message: detail } = await parseDispatchBody(res);
  if (!res.ok || success === false) throw new Error(detail ?? 'Failed to claim the request.');
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
  // The cast panel's "+ Add NPC" arrives with ?scene=<id> (#4418).
  const [searchParams] = useSearchParams();
  const sceneParam = Number(searchParams.get('scene'));
  const sceneId = Number.isInteger(sceneParam) && sceneParam > 0 ? sceneParam : null;
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['gm-dashboard'],
    queryFn: getGMDashboard,
    throwOnError: false,
  });
  // #4188: asked once the dashboard answered, which is the proof the viewer
  // is a GM (the attention endpoint 403s everyone else the same way).
  const { data: attention } = useGMAttention(data !== undefined);

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
      queryClient.invalidateQueries({ queryKey: gmKeys.attention }).catch(() => {});
    },
  });

  // "My NPCs" (#3426) — the account's own Story NPC tenures, split out of the
  // general character list client-side (no dedicated backend endpoint needed).
  const { data: myRosterEntries = [] } = useMyRosterEntriesQuery();
  const myNpcs = myRosterEntries.filter((entry) => entry.roster_type === 'NPC');
  const [managedNpcId, setManagedNpcId] = useState<number | null>(null);

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
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">GM Dashboard</h1>
        <Button asChild size="sm" variant="outline">
          <Link to="/gm/story-builder">Story Builder</Link>
        </Button>
      </div>

      {/* Waiting on you (#4188): the strip the page opens on. */}
      {attention ? <WaitingOnYouStrip attention={attention} /> : null}

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

      {/* GM prompt settings (#4101, demo Screen 5) */}
      <GMPromptFilterCard />

      {/* My tables */}
      <section className="rounded-lg border p-4">
        <h2 className="mb-2 text-lg font-semibold">My Tables ({data.my_tables.length})</h2>
        {data.my_tables.length === 0 ? (
          <p className="text-sm text-muted-foreground">No active tables.</p>
        ) : (
          <ul className="space-y-1 text-sm">
            {data.my_tables.map((table) => (
              <li key={table.id}>
                <span className="font-medium">{table.name}</span>: {table.membership_count}{' '}
                member(s)
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* My NPCs (#3426) — Story NPCs minted directly by this GM, tenure-bound
          to their own account. Playing one needs no new UI: the persona
          picker already lists it once minted. */}
      <section className="rounded-lg border p-4">
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-lg font-semibold">My NPCs ({myNpcs.length})</h2>
          <Button asChild size="sm" variant="outline">
            <Link to="/gm/npcs">NPC roster</Link>
          </Button>
        </div>
        {myNpcs.length === 0 ? (
          <p className="text-sm text-muted-foreground">No Story NPCs yet.</p>
        ) : (
          <ul className="space-y-1 text-sm">
            {myNpcs.map((entry) => (
              <li key={entry.id} className="space-y-2">
                <div className="flex items-center gap-3">
                  <Link to={`/characters/${entry.id}`} className="font-medium hover:underline">
                    {entry.name}
                  </Link>
                  {entry.loan === null && (
                    <Button
                      size="sm"
                      variant="outline"
                      aria-expanded={managedNpcId === entry.id}
                      onClick={() => setManagedNpcId(managedNpcId === entry.id ? null : entry.id)}
                    >
                      {managedNpcId === entry.id ? 'Close' : `Manage ${entry.name}`}
                    </Button>
                  )}
                </div>
                {managedNpcId === entry.id && (
                  <NpcOwnerPanel entryId={entry.id} name={entry.name} />
                )}
              </li>
            ))}
          </ul>
        )}
        <div className="mt-4 border-t pt-4" id="new-npc">
          <NpcForm mode="quick" sceneId={sceneId} />
        </div>
      </section>

      {/* Stat tiles. Pending AGM claims and assigned sessions moved to the
          strip above (#4188), where they have doors. */}
      <section className="grid grid-cols-2 gap-4">
        <div className="rounded-lg border p-4">
          <p className="text-sm text-muted-foreground">Episodes ready to run</p>
          <p className="text-2xl font-bold">{data.episodes_ready_to_run.length}</p>
        </div>
        <div className="rounded-lg border p-4">
          <p className="text-sm text-muted-foreground">Stories waiting on you</p>
          <p className="text-2xl font-bold">{data.waiting_for_gm.length}</p>
        </div>
        {/* Pending applications + open invites (#3268) — GM-owned roster creation
            surface. Both counts are reviewed/managed from the per-table
            Recruitment tab, not this dashboard, so both link to /tables. */}
        <Link
          to="/tables"
          className="rounded-lg border p-4 transition-colors hover:bg-accent"
          data-testid="pending-applications-tile"
        >
          <p className="text-sm text-muted-foreground">Pending applications</p>
          <p className="text-2xl font-bold">{data.pending_applications}</p>
        </Link>
        <Link
          to="/tables"
          className="rounded-lg border p-4 transition-colors hover:bg-accent"
          data-testid="open-invites-tile"
        >
          <p className="text-sm text-muted-foreground">Open invites</p>
          <p className="text-2xl font-bold">{data.open_invites}</p>
        </Link>
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

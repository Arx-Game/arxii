/**
 * GMDashboardPage — the GM's story-shaped dashboard (#2004).
 *
 * Shows the GM's tables, upcoming sessions, stories needing attention,
 * pending AGM claims, pending story offers, evidence summary, and (#3426)
 * the GM's own Story NPCs + a mint dialog, from GET /api/gm/dashboard/ plus
 * GET /api/roster/entries/mine/.
 *
 * Permission gating: the endpoint returns 403 for non-GMs. We use a local
 * query with throwOnError: false so we can render a friendly "not a GM" page
 * rather than blowing the error boundary.
 */

import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';
import { Textarea } from '@/components/ui/textarea';
import { apiFetch } from '@/evennia_replacements/api';
import { parseDispatchBody } from '@/lib/errors';
import { useMyRosterEntriesQuery } from '@/roster/queries';
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

/**
 * Dispatch MintStoryNPCAction as the actor's own character (#3426) — mints a
 * Story NPC tenure-bound to the GM's own account, playable immediately via
 * the persona picker / telnet `@ic`. Mirrors claimGroupStoryRequest's dispatch
 * shape; `success === false` (not just `res.ok`) signals a refusal (trust
 * gate or cap), per the same #3155 contract.
 *
 * `preset`, when given (#3427), names a curated `NPCStatlinePreset` by
 * natural key — the same string the telnet `gm npc ... preset=<name>`
 * grammar takes.
 */
async function mintStoryNpc(
  characterId: number,
  name: string,
  description: string,
  preset: string | null
): Promise<string> {
  const kwargs: Record<string, string> = { name, description };
  if (preset) kwargs.preset = preset;
  const res = await apiFetch(`/api/actions/characters/${characterId}/dispatch/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      ref: { backend: 'registry', registry_key: 'mint_story_npc' },
      kwargs,
    }),
  });
  const { success, message: detail } = await parseDispatchBody(res);
  if (!res.ok || success === false) throw new Error(detail ?? 'Failed to mint the NPC.');
  return detail ?? 'NPC minted.';
}

/** One curated statline preset in the GM mint dialog's picker (#3427). */
interface NPCStatlinePresetOption {
  id: number;
  name: string;
  description: string;
}

/**
 * Read-only preset catalog for the mint dialog's Select (GET
 * /api/roster/npc-presets/). No paging param: the ViewSet's page size (100)
 * already covers the whole starter catalog in one page.
 */
async function getNpcStatlinePresets(): Promise<NPCStatlinePresetOption[]> {
  const res = await apiFetch('/api/roster/npc-presets/');
  if (!res.ok) return [];
  const body = (await res.json()) as { results?: NPCStatlinePresetOption[] };
  return body.results ?? [];
}

/** Sentinel Select value for "no preset" — Radix Select rejects an empty-string item value. */
const NO_PRESET_VALUE = '__none__';

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

  // "My NPCs" (#3426) — the account's own Story NPC tenures, split out of the
  // general character list client-side (no dedicated backend endpoint needed).
  const { data: myRosterEntries = [] } = useMyRosterEntriesQuery();
  const myNpcs = myRosterEntries.filter((entry) => entry.roster_type === 'NPC');

  const [mintOpen, setMintOpen] = useState(false);
  const [npcName, setNpcName] = useState('');
  const [npcDescription, setNpcDescription] = useState('');
  const [npcPreset, setNpcPreset] = useState<string | null>(null);

  // Preset catalog (#3427) — only fetched once the dialog is open, since it's
  // a GM-only catalog with no reason to load before the GM asks to mint.
  const { data: presets = [] } = useQuery({
    queryKey: ['npc-statline-presets'],
    queryFn: getNpcStatlinePresets,
    enabled: mintOpen,
  });

  const mintMutation = useMutation({
    mutationFn: () => {
      if (actorCharacterId === null) {
        return Promise.reject(new Error('Puppet a character to mint an NPC.'));
      }
      return mintStoryNpc(actorCharacterId, npcName.trim(), npcDescription.trim(), npcPreset);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['my-roster-entries'] }).catch(() => {});
      setMintOpen(false);
      setNpcName('');
      setNpcDescription('');
      setNpcPreset(null);
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
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">GM Dashboard</h1>
        <Button asChild size="sm" variant="outline">
          <Link to="/gm/story-builder">Story Builder</Link>
        </Button>
      </div>

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
          <Dialog open={mintOpen} onOpenChange={setMintOpen}>
            <DialogTrigger asChild>
              <Button size="sm" variant="outline">
                Mint Story NPC
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Mint Story NPC</DialogTitle>
                <DialogDescription>
                  Create a Story NPC bound to your account — playable immediately via the persona
                  picker or telnet @ic. Bounded by your GM level's cap.
                </DialogDescription>
              </DialogHeader>
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  mintMutation.mutate();
                }}
                className="space-y-4"
              >
                <div className="space-y-1">
                  <Label htmlFor="mint-npc-name">Name *</Label>
                  <Input
                    id="mint-npc-name"
                    value={npcName}
                    onChange={(e) => setNpcName(e.target.value)}
                    placeholder="e.g. Master Aldous"
                    required
                  />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="mint-npc-description">
                    Description{' '}
                    <span className="font-normal text-muted-foreground">(optional)</span>
                  </Label>
                  <Textarea
                    id="mint-npc-description"
                    value={npcDescription}
                    onChange={(e) => setNpcDescription(e.target.value)}
                    rows={3}
                    className="resize-y"
                  />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="mint-npc-preset">
                    Statline preset{' '}
                    <span className="font-normal text-muted-foreground">(optional)</span>
                  </Label>
                  <Select
                    value={npcPreset ?? NO_PRESET_VALUE}
                    onValueChange={(val) => setNpcPreset(val === NO_PRESET_VALUE ? null : val)}
                  >
                    <SelectTrigger id="mint-npc-preset">
                      <SelectValue placeholder="No preset (blank sheet)" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value={NO_PRESET_VALUE}>No preset (blank sheet)</SelectItem>
                      {presets.map((preset) => (
                        <SelectItem key={preset.id} value={preset.name}>
                          {preset.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                {mintMutation.isError && (
                  <p className="text-sm text-destructive">
                    {(mintMutation.error as Error).message}
                  </p>
                )}
                <DialogFooter>
                  <Button type="button" variant="outline" onClick={() => setMintOpen(false)}>
                    Cancel
                  </Button>
                  <Button
                    type="submit"
                    disabled={npcName.trim().length === 0 || mintMutation.isPending}
                  >
                    {mintMutation.isPending ? 'Minting…' : 'Mint'}
                  </Button>
                </DialogFooter>
              </form>
            </DialogContent>
          </Dialog>
        </div>
        {myNpcs.length === 0 ? (
          <p className="text-sm text-muted-foreground">No Story NPCs yet.</p>
        ) : (
          <ul className="space-y-1 text-sm">
            {myNpcs.map((entry) => (
              <li key={entry.id}>
                <Link to={`/characters/${entry.id}`} className="font-medium hover:underline">
                  {entry.name}
                </Link>
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
                <span className="font-medium">{offer.story__title}</span> -{' '}
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

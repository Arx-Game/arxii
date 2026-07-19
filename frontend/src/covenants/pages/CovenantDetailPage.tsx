/**
 * CovenantDetailPage — full covenant detail view.
 *
 * Shows:
 *  - Covenant name, type, sworn_objective, member count
 *  - Member roster: character name + role + engagement state
 *    - For own memberships: per-row Engage/Disengage button
 *      (disabled with tooltip when can_engage=false, showing engage_blocked_reason)
 *  - "Induct New Member" CTA (visible to active members) that opens
 *    RitualSessionDraftDialog with the Covenant Induction ritual
 *
 * Route: /covenants/:id
 */

import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useSelector } from 'react-redux';
import type { RootState } from '@/store/store';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { Skeleton } from '@/components/ui/skeleton';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog';
import {
  useCovenantDetail,
  useCovenantMembers,
  useEngageMembership,
  useDisengageMembership,
  useLeaveMembership,
  useKickMember,
  useCovenantRanks,
  useAssignMemberToRank,
} from '@/covenants/queries';
import { useRituals } from '@/rituals/queries';
import { RitualSessionDraftDialog } from '@/rituals/components/RitualSessionDraftDialog';
import { BattleStateBanner } from '@/covenants/components/BattleStateBanner';
import { GroupStoryRequestPanel } from '@/covenants/components/GroupStoryRequestPanel';
import { RitesPanel } from '@/covenants/components/RitesPanel';
import { RolePowersPanel } from '@/covenants/components/RolePowersPanel';
import { PromoteRoleDialog } from '@/covenants/components/PromoteRoleDialog';
import { RankManagementPanel } from '@/covenants/components/RankManagementPanel';
import type { CharacterCovenantRole, CovenantRank, ViewerCapabilities } from '@/covenants/api';
import type { RitualWithSchema, RitualInputSchema } from '@/rituals/types';

// ---------------------------------------------------------------------------
// Loading skeleton
// ---------------------------------------------------------------------------

function DetailSkeleton() {
  return (
    <div className="animate-pulse space-y-6">
      <div className="space-y-2">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-4 w-40" />
        <Skeleton className="h-4 w-full" />
      </div>
      <div className="space-y-3">
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} className="h-14 w-full" />
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Helper: summarize a role's combat-identity blend for display
// ---------------------------------------------------------------------------

function blendSummary(role: {
  sword_weight: string;
  shield_weight: string;
  crown_weight: string;
}): string {
  const axes: Array<[string, number]> = [
    ['Sword', Number(role.sword_weight)],
    ['Shield', Number(role.shield_weight)],
    ['Crown', Number(role.crown_weight)],
  ];
  return (
    axes
      .filter(([, w]) => w > 0)
      .map(([label, w]) => `${label} ${Math.round(w * 100)}%`)
      .join(' · ') || 'Unaligned'
  );
}

// ---------------------------------------------------------------------------
// Member row
// ---------------------------------------------------------------------------

interface MemberRowProps {
  membership: CharacterCovenantRole;
  isOwnMembership: boolean;
  viewerCapabilities: ViewerCapabilities;
  viewerRankTier: number;
  covenantId: number;
  ranks: CovenantRank[];
}

function MemberRow({
  membership,
  isOwnMembership,
  viewerCapabilities,
  viewerRankTier,
  covenantId,
  ranks,
}: MemberRowProps) {
  const engage = useEngageMembership(covenantId);
  const disengage = useDisengageMembership(covenantId);
  const leave = useLeaveMembership(covenantId);
  const kick = useKickMember(covenantId);
  const assignRank = useAssignMemberToRank(covenantId);
  const isBusy = engage.isPending || disengage.isPending;
  const [promoteOpen, setPromoteOpen] = useState(false);

  const role = membership.covenant_role;
  const characterSheetId = membership.character_sheet;
  const isBlocked = membership.display_name === 'a member has blocked you';
  // can_kick is true when: viewer has the capability, target is not own row, target is active,
  // and target has a strictly higher tier number (lower authority) than the viewer.
  const canKick =
    viewerCapabilities.can_kick &&
    !isOwnMembership &&
    membership.is_active &&
    membership.rank.tier > viewerRankTier &&
    !isBlocked;
  // Rank assignment (promote/demote) is offered to managers on any active member.
  const canAssignRank =
    viewerCapabilities.can_manage_ranks && membership.is_active && ranks.length > 0 && !isBlocked;

  function handleAssignRank(rankId: number) {
    if (rankId !== membership.rank.id) {
      assignRank.mutate({ rankId, membershipId: membership.id });
    }
  }

  function handleEngage() {
    engage.mutate(membership.id);
  }

  function handleDisengage() {
    disengage.mutate(membership.id);
  }

  function handleLeave() {
    leave.mutate(membership.id);
  }

  function handleKick() {
    kick.mutate(membership.id);
  }

  return (
    <div
      className={`flex items-center justify-between gap-4 rounded-md border px-4 py-3${isBlocked ? 'opacity-50' : ''}`}
      data-testid="member-row"
    >
      <div className="min-w-0 flex-1 space-y-0.5">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-medium">
            {membership.display_name ?? `Character #${characterSheetId}`}
          </span>
          <Badge variant="secondary" className="text-xs">
            {membership.rank.name}
          </Badge>
          <Badge variant="outline" className="text-xs">
            {role.name}
          </Badge>
          <Badge variant="outline" className="text-xs">
            {blendSummary(role)}
          </Badge>
          {membership.engaged && (
            <Badge variant="default" className="text-xs">
              Engaged
            </Badge>
          )}
        </div>
        <p className="text-xs text-muted-foreground">
          Joined {new Date(membership.joined_at).toLocaleDateString()}
          {!membership.is_active && membership.left_at
            ? ` · Left ${new Date(membership.left_at).toLocaleDateString()}`
            : ''}
        </p>
      </div>

      {isOwnMembership && membership.is_active && (
        <div className="flex shrink-0 flex-col items-end gap-1">
          <div className="flex items-center gap-2">
            {membership.engaged ? (
              <Button size="sm" variant="outline" onClick={handleDisengage} disabled={isBusy}>
                {disengage.isPending ? 'Disengaging…' : 'Disengage'}
              </Button>
            ) : (
              <Button
                size="sm"
                variant="outline"
                onClick={handleEngage}
                disabled={isBusy || !membership.can_engage}
                title={
                  !membership.can_engage && membership.engage_blocked_reason
                    ? membership.engage_blocked_reason
                    : undefined
                }
              >
                {engage.isPending ? 'Engaging…' : 'Engage'}
              </Button>
            )}
            <Button size="sm" variant="outline" onClick={() => setPromoteOpen(true)}>
              Promote
            </Button>
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button
                  size="sm"
                  variant="destructive"
                  data-testid="leave-button"
                  disabled={leave.isPending}
                >
                  {leave.isPending ? 'Leaving…' : 'Leave'}
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Leave this covenant?</AlertDialogTitle>
                  <AlertDialogDescription>
                    If this drops the covenant below 2 members, it will dissolve.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Cancel</AlertDialogCancel>
                  <AlertDialogAction onClick={handleLeave}>Leave</AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          </div>
          {!membership.can_engage && membership.engage_blocked_reason && !membership.engaged && (
            <p className="text-xs text-muted-foreground">{membership.engage_blocked_reason}</p>
          )}
          <PromoteRoleDialog
            covenantId={covenantId}
            membership={membership}
            open={promoteOpen}
            onOpenChange={setPromoteOpen}
          />
        </div>
      )}

      {canAssignRank && (
        <div className="flex shrink-0 flex-col items-end gap-1">
          <label htmlFor={`assign-rank-${membership.id}`} className="sr-only">
            Assign rank for member {characterSheetId}
          </label>
          <select
            id={`assign-rank-${membership.id}`}
            data-testid="assign-rank-select"
            className="h-9 rounded-md border bg-background px-2 text-sm"
            value={membership.rank.id}
            disabled={assignRank.isPending}
            onChange={(e) => handleAssignRank(Number(e.target.value))}
          >
            {ranks.map((rank) => (
              <option key={rank.id} value={rank.id}>
                {rank.name} (tier {rank.tier})
              </option>
            ))}
          </select>
        </div>
      )}

      {canKick && (
        <div className="flex shrink-0 flex-col items-end gap-1">
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button
                size="sm"
                variant="destructive"
                data-testid="kick-button"
                disabled={kick.isPending}
              >
                {kick.isPending ? 'Removing…' : 'Remove'}
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Remove this member?</AlertDialogTitle>
                <AlertDialogDescription>
                  Remove this {role.name} from the covenant.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Cancel</AlertDialogCancel>
                <AlertDialogAction onClick={handleKick}>Remove</AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Helper: find the Covenant Induction ritual by name
// ---------------------------------------------------------------------------

function findInductionRitual(rituals: RitualWithSchema[]): RitualWithSchema | null {
  return (
    rituals.find(
      (r) => r.name === 'Covenant Induction' && (r.participation_rule as string) === 'INDUCTION'
    ) ?? null
  );
}

// ---------------------------------------------------------------------------
// Inner page
// ---------------------------------------------------------------------------

export function CovenantDetailInner({ covenantId }: { covenantId: number }) {
  const navigate = useNavigate();
  const account = useSelector((state: RootState) => state.auth.account);

  const activeCharacter =
    account?.available_characters?.find((c) => c.currently_puppeted_in_session) ?? null;
  const characterSheetId = activeCharacter?.id ?? null;

  const { data: covenant, isLoading: covenantLoading } = useCovenantDetail(covenantId);
  const { data: membersPage, isLoading: membersLoading } = useCovenantMembers(covenantId);
  const { data: ranksPage } = useCovenantRanks(covenantId);
  const { data: ritualsData, isLoading: ritualsLoading } = useRituals();

  const [inductionOpen, setInductionOpen] = useState(false);

  if (covenantLoading || membersLoading) return <DetailSkeleton />;

  if (!covenant) {
    return <p className="py-8 text-center text-muted-foreground">Covenant not found.</p>;
  }

  const members = membersPage?.results ?? [];
  const activeMembers = members.filter((m) => m.is_active);

  // Determine if current character is an active member
  const ownMembership = characterSheetId
    ? (activeMembers.find((m) => m.character_sheet === characterSheetId) ?? null)
    : null;

  const isActiveMember = ownMembership !== null;

  // viewer_capabilities is the same value on every row in one covenant (server memoizes it);
  // read it from the first result. The generated schema type (ViewerCapabilitiesSerializer)
  // hasn't been regenerated on this branch to include can_request_gm (#2119) yet — cast to
  // the hand-extended local type; the backend already serializes the field at runtime.
  const viewerCapabilities: ViewerCapabilities = (membersPage?.results?.[0]?.viewer_capabilities as
    | ViewerCapabilities
    | undefined) ?? {
    can_invite: false,
    can_kick: false,
    can_manage_ranks: false,
    can_request_gm: false,
  };

  // Viewer's own rank tier (or Infinity = lowest authority if not a member).
  const viewerRankTier: number = ownMembership?.rank?.tier ?? Infinity;

  // The covenant's rank ladder, sorted by tier (highest authority first), for the
  // per-member rank-assignment picker.
  const ranks = [...(ranksPage?.results ?? [])].sort((a, b) => a.tier - b.tier);

  // Find induction ritual
  const allRituals = !ritualsLoading ? ((ritualsData?.results ?? []) as RitualWithSchema[]) : [];
  const inductionRitual = findInductionRitual(allRituals);

  return (
    <div className="space-y-6">
      {/* Battle-state banner (renders null for non-battle covenants) */}
      <BattleStateBanner
        covenant={covenant}
        characterSheetId={characterSheetId}
        isActiveMember={isActiveMember}
      />

      {/* Covenant header */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center gap-3">
            <CardTitle className="text-xl">{covenant.name}</CardTitle>
            <Badge variant="outline">{covenant.covenant_type_display}</Badge>
          </div>
        </CardHeader>
        <CardContent className="space-y-2">
          <p className="text-sm text-muted-foreground">
            {covenant.member_count} {covenant.member_count === 1 ? 'member' : 'members'} · Level{' '}
            {covenant.level}
          </p>
          {covenant.sworn_objective && (
            <p className="rounded-md bg-muted px-3 py-2 text-sm italic">
              {covenant.sworn_objective}
            </p>
          )}
          {!covenant.is_active && (
            <Badge variant="destructive" className="mt-1">
              Dissolved
            </Badge>
          )}
        </CardContent>
      </Card>

      {/* Member roster */}
      <section>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-lg font-semibold">Members</h2>
          {viewerCapabilities.can_invite && inductionRitual && (
            <Button
              size="sm"
              onClick={() => setInductionOpen(true)}
              data-testid="induct-member-button"
            >
              Induct New Member
            </Button>
          )}
          {viewerCapabilities.can_invite && !ritualsLoading && !inductionRitual && (
            <Button size="sm" disabled title="Covenant Induction ritual not available">
              Induct New Member
            </Button>
          )}
        </div>

        {activeMembers.length === 0 ? (
          <p className="py-4 text-center text-sm text-muted-foreground">No active members.</p>
        ) : (
          <div className="space-y-2" data-testid="member-roster">
            {activeMembers.map((membership) => (
              <MemberRow
                key={membership.id}
                membership={membership}
                isOwnMembership={membership.character_sheet === characterSheetId}
                viewerCapabilities={viewerCapabilities}
                viewerRankTier={viewerRankTier}
                covenantId={covenantId}
                ranks={ranks}
              />
            ))}
          </div>
        )}
      </section>

      {/* Recruiting a GM (#2119) */}
      <section>
        <GroupStoryRequestPanel
          covenantId={covenantId}
          viewerCapabilities={viewerCapabilities}
          actorCharacterId={characterSheetId}
        />
      </section>

      {/* Covenant rites */}
      <section>
        <RitesPanel
          covenantId={covenantId}
          isActiveMember={isActiveMember}
          characterSheetId={characterSheetId}
        />
      </section>

      {/* Per-member passive role powers */}
      <section>
        <RolePowersPanel covenantId={covenantId} />
      </section>

      {/* Rank ladder management (visible to members with can_manage_ranks) */}
      <section>
        <RankManagementPanel covenantId={covenantId} viewerCapabilities={viewerCapabilities} />
      </section>

      {/* Induction dialog */}
      {inductionRitual && characterSheetId && (
        <RitualSessionDraftDialog
          ritual={inductionRitual as RitualWithSchema & { input_schema: RitualInputSchema | null }}
          characterSheetId={characterSheetId}
          sessionReferences={[{ kind: 'COVENANT', ref_covenant_id: covenantId }]}
          open={inductionOpen}
          onOpenChange={setInductionOpen}
          onSuccess={(session) => {
            setInductionOpen(false);
            navigate(`/rituals/sessions/${session.id}`);
          }}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page export
// ---------------------------------------------------------------------------

export function CovenantDetailPage() {
  const { id = '' } = useParams<{ id: string }>();
  const covenantId = parseInt(id, 10);

  if (isNaN(covenantId) || covenantId <= 0) {
    return (
      <div className="container mx-auto px-4 py-6 sm:px-6 sm:py-8 lg:px-8">
        <p className="text-muted-foreground">Invalid covenant ID.</p>
      </div>
    );
  }

  return (
    <div className="container mx-auto px-4 py-6 sm:px-6 sm:py-8 lg:px-8">
      <ErrorBoundary>
        <CovenantDetailInner covenantId={covenantId} />
      </ErrorBoundary>
    </div>
  );
}

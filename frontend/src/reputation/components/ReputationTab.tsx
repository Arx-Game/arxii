/**
 * Consolidated Reputation tab (#1446) — replaces the old standalone Renown tab.
 *
 * Own-view sections:
 *   - Renown: the existing `RenownPanel`, unchanged — fame/prestige/deeds/dwellings plus its
 *     own (unflagged) society-reputation card.
 *   - Standing: society reputation again, this time with "Wanted" flags for any society
 *     currently pursuing the viewer's active persona (#1765 heat), plus organization
 *     memberships (rank titles) and organization reputation (tier badges).
 *   - Covenants: the character's active covenant role assignments.
 *
 * Foreign-view: unchanged `RenownCardPanel` — no Standing/Covenants/Wanted surfaced for
 * someone else's sheet.
 *
 * The society-reputation list is necessarily rendered twice (once inside `RenownPanel`,
 * once here with wanted flags) — `RenownPanel` is intentionally left untouched by this task,
 * so the wanted-aware view lives in the new Standing card instead of being threaded through it.
 */

import { Link } from 'react-router-dom';
import { Loader2 } from 'lucide-react';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { RenownPanel } from '@/renown/components/RenownPanel';
import { RenownCardPanel } from '@/renown/components/RenownCardPanel';
import {
  ReputationListCard,
  TIER_VARIANT,
  formatTier,
} from '@/renown/components/ReputationListCard';
import { usePersonaRenownQuery } from '@/renown/queries';
import { usePersonaHeat } from '@/justice/queries';
import type { PersonaHeatRow } from '@/justice/api';
import type { CharacterCovenantRole } from '@/covenants/api';

import {
  useOrganizationMembershipsQuery,
  useOrganizationReputationsQuery,
  useCovenantRolesQuery,
} from '../queries';

interface Props {
  /** CharacterSheet pk of the character this sheet is showing. */
  entryCharacterId: number;
  /** The viewer's own currently-presented persona; null/undefined when unknown. */
  viewerPersonaId?: number | null;
  /** True when the viewer owns this character (own-view vs. foreign-view). */
  isMyCharacter: boolean;
  /** The viewer's active RosterEntry pk; used to key the own-only wanted-flag lookup. */
  viewerEntryId?: number | null;
}

export function ReputationTab({
  entryCharacterId,
  viewerPersonaId,
  isMyCharacter,
  viewerEntryId,
}: Props) {
  if (!isMyCharacter) {
    return (
      <RenownCardPanel
        characterSheetId={entryCharacterId}
        viewerPersonaId={viewerPersonaId ?? null}
      />
    );
  }

  return (
    <OwnReputationView
      entryCharacterId={entryCharacterId}
      viewerPersonaId={viewerPersonaId ?? null}
      viewerEntryId={viewerEntryId ?? null}
    />
  );
}

function OwnReputationView({
  entryCharacterId,
  viewerPersonaId,
  viewerEntryId,
}: {
  entryCharacterId: number;
  viewerPersonaId: number | null;
  viewerEntryId: number | null;
}) {
  return (
    <div className="space-y-6">
      <section aria-labelledby="reputation-tab-renown">
        <h2 id="reputation-tab-renown" className="mb-3 text-lg font-semibold">
          Renown
        </h2>
        <RenownPanel characterSheetId={entryCharacterId} />
      </section>

      <section aria-labelledby="reputation-tab-standing">
        <h2 id="reputation-tab-standing" className="mb-3 text-lg font-semibold">
          Standing
        </h2>
        <StandingSection viewerPersonaId={viewerPersonaId} viewerEntryId={viewerEntryId} />
      </section>

      <section aria-labelledby="reputation-tab-covenants">
        <h2 id="reputation-tab-covenants" className="mb-3 text-lg font-semibold">
          Covenants
        </h2>
        <CovenantsCard characterSheetId={entryCharacterId} />
      </section>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Standing — society reputation (wanted-flag aware) + org memberships/reputation.
// ---------------------------------------------------------------------------

function StandingSection({
  viewerPersonaId,
  viewerEntryId,
}: {
  viewerPersonaId: number | null;
  viewerEntryId: number | null;
}) {
  const { data: renown } = usePersonaRenownQuery(viewerPersonaId);
  const { data: heatRows } = usePersonaHeat(viewerEntryId);
  const wantedSocietyIds = new Set<number>(
    (heatRows ?? []).map((row: PersonaHeatRow) => row.society)
  );

  return (
    <div className="grid gap-4 md:grid-cols-2">
      <ReputationListCard
        reputation={renown?.reputation ?? []}
        wantedSocietyIds={wantedSocietyIds}
      />
      <OrganizationStandingCard />
    </div>
  );
}

function OrganizationStandingCard() {
  const { data: memberships, isLoading: membershipsLoading } =
    useOrganizationMembershipsQuery(true);
  const { data: reputations, isLoading: reputationsLoading } =
    useOrganizationReputationsQuery(true);

  const isLoading = membershipsLoading || reputationsLoading;
  const activeMemberships = (memberships ?? []).filter((m) => m.is_active);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Organizations</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {isLoading ? (
          <div className="flex justify-center py-4">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        ) : (
          <>
            <div>
              <h3 className="mb-2 text-sm font-medium text-muted-foreground">Memberships</h3>
              {activeMemberships.length === 0 ? (
                <p className="text-sm text-muted-foreground">No active organization memberships.</p>
              ) : (
                <ul className="space-y-2 text-sm">
                  {activeMemberships.map((membership) => (
                    <li key={membership.id} className="flex items-center justify-between">
                      <Link
                        to={`/orgs/${membership.organization}`}
                        className="font-medium hover:underline"
                      >
                        {membership.organization_name}
                      </Link>
                      <Badge variant="outline">{membership.title}</Badge>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <div>
              <h3 className="mb-2 text-sm font-medium text-muted-foreground">Reputation</h3>
              {(reputations ?? []).length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No organizations have a recorded opinion yet.
                </p>
              ) : (
                <ul className="space-y-2 text-sm">
                  {(reputations ?? []).map((rep) => (
                    <li key={rep.id} className="flex items-center justify-between">
                      <Link
                        to={`/orgs/${rep.organization}`}
                        className="font-medium hover:underline"
                      >
                        {rep.organization_name}
                      </Link>
                      <Badge variant={TIER_VARIANT[rep.tier] ?? 'outline'}>
                        {formatTier(rep.tier)}
                      </Badge>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Covenants — active covenant role assignments for this character sheet.
// ---------------------------------------------------------------------------

function CovenantsCard({ characterSheetId }: { characterSheetId: number }) {
  const { data: roles, isLoading } = useCovenantRolesQuery(characterSheetId);
  const activeRoles = (roles ?? []).filter((r: CharacterCovenantRole) => r.is_active);

  return (
    <Card>
      <CardContent className="py-4">
        {isLoading ? (
          <div className="flex justify-center py-4">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        ) : activeRoles.length === 0 ? (
          <p className="text-sm text-muted-foreground">No active covenant roles.</p>
        ) : (
          <ul className="space-y-2 text-sm">
            {activeRoles.map((role) => (
              <li key={role.id} className="flex items-center justify-between">
                <Link to={`/covenants/${role.covenant}`} className="font-medium hover:underline">
                  {role.covenant_role.name}
                </Link>
                <div className="flex items-center gap-2">
                  {role.engaged && <Badge variant="default">Engaged</Badge>}
                  <Badge variant="outline">{role.rank.name}</Badge>
                </div>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

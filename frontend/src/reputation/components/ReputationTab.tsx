/**
 * Consolidated Reputation tab (#1446) — replaces the old standalone Renown tab.
 *
 * Own-view sections:
 *   - Renown: the existing `RenownPanel`, fed the viewed character's wanted-flag data
 *     (#1765 heat) — fame/prestige/deeds/dwellings plus its own society-reputation card,
 *     with a destructive "Wanted" badge on any society currently pursuing this character.
 *   - Standing: organization memberships (rank titles) and organization reputation (tier
 *     badges) for the character being viewed.
 *   - Covenants: the character's active covenant role assignments.
 *
 * Foreign-view: unchanged `RenownCardPanel` — no Standing/Covenants/Wanted surfaced for
 * someone else's sheet.
 *
 * Scoping note: `/api/societies/reputations/` and `/api/societies/memberships/` are
 * account-wide (span every character/persona the account plays), not sheet-scoped —
 * unlike the covenant-roles endpoint, which already filters by `character_sheet`. So the
 * membership/reputation rows are filtered client-side to `viewedPersonaId` to avoid
 * leaking a different one of the viewer's own characters' standings onto this sheet.
 */

import { Link } from 'react-router-dom';
import { Loader2 } from 'lucide-react';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { RenownPanel } from '@/renown/components/RenownPanel';
import { RenownCardPanel } from '@/renown/components/RenownCardPanel';
import { TIER_VARIANT, formatTier } from '@/renown/components/ReputationListCard';
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
  /**
   * RosterEntry pk of the character being viewed. Own-view only — used to key the
   * wanted-flag heat lookup to THIS character, not whichever character the account
   * currently has active (matches the `viewer=` param CrimeTab passes).
   */
  viewedEntryId?: number | null;
  /**
   * Persona id of the character being viewed. Own-view only — used to filter the
   * account-wide org membership/reputation rows down to this character's persona.
   */
  viewedPersonaId?: number | null;
}

export function ReputationTab({
  entryCharacterId,
  viewerPersonaId,
  isMyCharacter,
  viewedEntryId,
  viewedPersonaId,
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
      viewedEntryId={viewedEntryId ?? null}
      viewedPersonaId={viewedPersonaId ?? null}
    />
  );
}

function OwnReputationView({
  entryCharacterId,
  viewedEntryId,
  viewedPersonaId,
}: {
  entryCharacterId: number;
  viewedEntryId: number | null;
  viewedPersonaId: number | null;
}) {
  const { data: heatRows } = usePersonaHeat(viewedEntryId);
  const wantedSocietyIds = new Set<number>(
    (heatRows ?? []).map((row: PersonaHeatRow) => row.society)
  );

  return (
    <div className="space-y-6">
      <section aria-labelledby="reputation-tab-renown">
        <h2 id="reputation-tab-renown" className="mb-3 text-lg font-semibold">
          Renown
        </h2>
        <RenownPanel characterSheetId={entryCharacterId} wantedSocietyIds={wantedSocietyIds} />
      </section>

      <section aria-labelledby="reputation-tab-standing">
        <h2 id="reputation-tab-standing" className="mb-3 text-lg font-semibold">
          Standing
        </h2>
        <OrganizationStandingCard viewedPersonaId={viewedPersonaId} />
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
// Standing — org memberships/reputation, scoped to the viewed character's persona.
// ---------------------------------------------------------------------------

function OrganizationStandingCard({ viewedPersonaId }: { viewedPersonaId: number | null }) {
  const { data: memberships, isLoading: membershipsLoading } =
    useOrganizationMembershipsQuery(true);
  const { data: reputations, isLoading: reputationsLoading } =
    useOrganizationReputationsQuery(true);

  const isLoading = membershipsLoading || reputationsLoading;
  const activeMemberships = (memberships ?? []).filter(
    (m) => m.is_active && m.persona === viewedPersonaId
  );
  const scopedReputations = (reputations ?? []).filter((r) => r.persona === viewedPersonaId);

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
              {scopedReputations.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No organizations have a recorded opinion yet.
                </p>
              ) : (
                <ul className="space-y-2 text-sm">
                  {scopedReputations.map((rep) => (
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

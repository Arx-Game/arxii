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
 *
 * Drawn in the Reference Sheet's vocabulary (#3898): subheadings over entries on
 * hairlines, with the rank or tier as the row's tag. The sheet supplies "Standing"
 * above all of it, so nothing here draws a heading at that weight.
 */

import { Link } from 'react-router-dom';

import { RenownPanel } from '@/renown/components/RenownPanel';
import { RenownCardPanel } from '@/renown/components/RenownCardPanel';
import { formatTier } from '@/renown/components/ReputationListCard';
import {
  Entries,
  Entry,
  Ledger,
  Stack,
  Subheading,
  Tag,
} from '@/character_sheets/components/sheet/primitives';
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
    <Stack wide>
      <Stack>
        <Subheading>Renown</Subheading>
        <RenownPanel characterSheetId={entryCharacterId} wantedSocietyIds={wantedSocietyIds} />
      </Stack>

      <OrganizationStandingBlock viewedPersonaId={viewedPersonaId} />

      <Stack>
        <Subheading>Covenants</Subheading>
        <CovenantRoles characterSheetId={entryCharacterId} />
      </Stack>
    </Stack>
  );
}

// ---------------------------------------------------------------------------
// Standing — org memberships/reputation, scoped to the viewed character's persona.
// ---------------------------------------------------------------------------

function OrganizationStandingBlock({ viewedPersonaId }: { viewedPersonaId: number | null }) {
  const { data: memberships, isLoading: membershipsLoading } =
    useOrganizationMembershipsQuery(true);
  const { data: reputations, isLoading: reputationsLoading } =
    useOrganizationReputationsQuery(true);

  const isLoading = membershipsLoading || reputationsLoading;
  const activeMemberships = (memberships ?? []).filter(
    (m) => m.is_active && m.persona === viewedPersonaId
  );
  const scopedReputations = (reputations ?? []).filter((r) => r.persona === viewedPersonaId);

  if (isLoading) {
    return <Ledger>Reading where they stand…</Ledger>;
  }

  return (
    <Stack wide>
      <Stack>
        <Subheading>Belongs to</Subheading>
        {activeMemberships.length === 0 ? (
          <Ledger>They belong to nobody.</Ledger>
        ) : (
          <Entries>
            {activeMemberships.map((membership) => (
              <Entry
                key={membership.id}
                name={
                  <Link to={`/orgs/${membership.organization}`}>
                    {membership.organization_name}
                  </Link>
                }
                aside={<span className="refsheet-note">{membership.title}</span>}
              />
            ))}
          </Entries>
        )}
      </Stack>
      <Stack>
        <Subheading>Thought of as</Subheading>
        {scopedReputations.length === 0 ? (
          <Ledger>No organization has an opinion of them yet.</Ledger>
        ) : (
          <Entries>
            {scopedReputations.map((rep) => (
              <Entry
                key={rep.id}
                name={<Link to={`/orgs/${rep.organization}`}>{rep.organization_name}</Link>}
                tags={<Tag accent>{formatTier(rep.tier)}</Tag>}
              />
            ))}
          </Entries>
        )}
      </Stack>
    </Stack>
  );
}

// ---------------------------------------------------------------------------
// Covenants — active covenant role assignments for this character sheet.
// ---------------------------------------------------------------------------

function CovenantRoles({ characterSheetId }: { characterSheetId: number }) {
  const { data: roles, isLoading } = useCovenantRolesQuery(characterSheetId);
  const activeRoles = (roles ?? []).filter((r: CharacterCovenantRole) => r.is_active);

  if (isLoading) {
    return <Ledger>Reading their covenants…</Ledger>;
  }
  if (activeRoles.length === 0) {
    return <Ledger>They hold no covenant role.</Ledger>;
  }
  return (
    <Entries>
      {activeRoles.map((role) => (
        <Entry
          key={role.id}
          name={<Link to={`/covenants/${role.covenant}`}>{role.covenant_role.name}</Link>}
          aside={<span className="refsheet-note">{role.rank.name}</span>}
          tags={role.engaged ? <Tag accent>Engaged</Tag> : undefined}
        />
      ))}
    </Entries>
  );
}

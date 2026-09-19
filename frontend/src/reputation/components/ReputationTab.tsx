/**
 * Consolidated Reputation tab (#1446) — replaces the old standalone Renown tab.
 *
 * Own-view sections:
 *   - Renown: the existing `RenownPanel`, fed the viewed character's wanted-flag data
 *     (#1765 heat) — fame/prestige/deeds/dwellings plus its own society-reputation card,
 *     with a destructive "Wanted" badge on any society currently pursuing this character.
 *   - Standing: organization memberships (rank titles) and organization reputation (tier
 *     badges) for the character being viewed.
 *
 * Foreign-view: `RenownCardPanel` in place of the full panel, and no wanted flag — who
 * is hunting someone is theirs alone. Standing is drawn either way.
 *
 * Scoping note (#3906): standing and covenant roles arrive on the SHEET payload, built
 * off the presented persona and already gated by `standing_visibility` server-side. The
 * three account endpoints these blocks used to call — `/api/societies/memberships/`,
 * `/api/societies/reputations/` and the covenant-roles list — only ever answer for the
 * REQUESTER's own characters, so as a visitor they returned nothing, and as the owner
 * they returned every character the account plays and had to be filtered here. Reading
 * the payload fixes both halves at once: the server is the gate.
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
  Stack,
  Subheading,
  Tag,
} from '@/character_sheets/components/sheet/primitives';
import { usePersonaHeat } from '@/justice/queries';
import type { CharacterSheetCovenantRole, CharacterSheetStanding } from '@/character_sheets/api';
import type { PersonaHeatRow } from '@/justice/api';

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
   * Where this character stands, from the sheet payload (#3906). The server has
   * already applied `standing_visibility`, so an empty pair is all a withheld section
   * ever looks like from here — see `OrganizationStandingBlock` for why that settles
   * how it draws.
   */
  standing: CharacterSheetStanding;
}

export function ReputationTab({
  entryCharacterId,
  viewerPersonaId,
  isMyCharacter,
  viewedEntryId,
  standing,
}: Props) {
  // Renown still branches on ownership: the owner's view carries the wanted flag,
  // which says who is hunting them and stays theirs alone. Standing no longer
  // branches here at all — the server already emptied it for a viewer below the
  // tier, so rendering what we are handed IS the gate (#3906).
  return (
    <Stack wide>
      {isMyCharacter ? (
        <OwnRenownView entryCharacterId={entryCharacterId} viewedEntryId={viewedEntryId ?? null} />
      ) : (
        <Stack>
          <Subheading>Renown</Subheading>
          <RenownCardPanel
            characterSheetId={entryCharacterId}
            viewerPersonaId={viewerPersonaId ?? null}
          />
        </Stack>
      )}
      <OrganizationStandingBlock standing={standing} />
    </Stack>
  );
}

function OwnRenownView({
  entryCharacterId,
  viewedEntryId,
}: {
  entryCharacterId: number;
  viewedEntryId: number | null;
}) {
  const { data: heatRows } = usePersonaHeat(viewedEntryId);
  const wantedSocietyIds = new Set<number>(
    (heatRows ?? []).map((row: PersonaHeatRow) => row.society)
  );

  return (
    <Stack>
      <Subheading>Renown</Subheading>
      <RenownPanel characterSheetId={entryCharacterId} wantedSocietyIds={wantedSocietyIds} />
    </Stack>
  );
}

// ---------------------------------------------------------------------------
// Standing — org memberships/reputation, scoped to the viewed character's persona.
// ---------------------------------------------------------------------------

/**
 * Render-or-vanish, and here that is a correctness rule rather than a style one.
 *
 * A withheld section and a genuinely empty one arrive identically — the server sends
 * an empty pair either way — so a line reading "They belong to nobody" would be a
 * flat lie on every stranger's view of a character who belongs to three houses. And
 * vanishing on both leaks nothing either: a viewer cannot tell a hidden rail from an
 * unaffiliated one, which is what a privacy tier is supposed to buy.
 *
 * (Titles beside it speaks a line when empty, and is right to: it is never withheld,
 * so its empty state is always the truth.)
 */
function OrganizationStandingBlock({ standing }: { standing: CharacterSheetStanding }) {
  if (standing.memberships.length === 0 && standing.reputations.length === 0) {
    return null;
  }
  return (
    <Stack wide>
      {standing.memberships.length > 0 && (
        <Stack>
          <Subheading>Belongs to</Subheading>
          <Entries>
            {standing.memberships.map((membership) => (
              <Entry
                key={membership.organization_id}
                name={
                  <Link to={`/orgs/${membership.organization_id}`}>{membership.organization}</Link>
                }
                aside={<span className="refsheet-note">{membership.title}</span>}
              />
            ))}
          </Entries>
        </Stack>
      )}
      {standing.reputations.length > 0 && (
        <Stack>
          <Subheading>Thought of as</Subheading>
          <Entries>
            {standing.reputations.map((rep) => (
              <Entry
                key={rep.organization_id}
                name={<Link to={`/orgs/${rep.organization_id}`}>{rep.organization}</Link>}
                tags={<Tag accent>{formatTier(rep.tier)}</Tag>}
              />
            ))}
          </Entries>
        </Stack>
      )}
    </Stack>
  );
}

// ---------------------------------------------------------------------------
// Covenants — active covenant role assignments for this character sheet.
// ---------------------------------------------------------------------------

/**
 * The covenant roles a character holds, from the sheet payload. PUBLIC (#3906) — a
 * covenant role is a thing a character IS in the world, the way a title is, and the
 * Titles block on the same rail has always been public.
 *
 * It reads the payload rather than `useCovenantRolesQuery` because that endpoint only
 * answers for sheets the REQUESTER plays, so asking it as a visitor returns nothing.
 *
 * Vanishes when there is nothing, like the standing block above it — most characters
 * hold no covenant role at all, so a line saying so would be the common case.
 */
export function CovenantRoles({ covenants }: { covenants: CharacterSheetCovenantRole[] }) {
  if (covenants.length === 0) {
    return null;
  }
  return (
    <Entries>
      {covenants.map((role) => (
        <Entry
          key={role.id}
          name={<Link to={`/covenants/${role.covenant_id}`}>{role.role}</Link>}
          aside={<span className="refsheet-note">{role.rank}</span>}
          tags={role.engaged ? <Tag accent>Engaged</Tag> : undefined}
        />
      ))}
    </Entries>
  );
}

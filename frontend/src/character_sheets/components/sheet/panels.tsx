/**
 * The remaining sections of the Reference Sheet (#3898).
 *
 * Each of these is a LAYOUT that places existing, working panels inside the sheet's
 * headings and rails. The regrouping is the point of this file: sixteen tabs became
 * eight sections, so Relationships / Kinship / Reputation / Titles are one page called
 * Ties, Secrets / Clues / Gossip are Knowledge, and Crime / Locations / Agreements join
 * the purse and the wardrobe as Holdings. Nothing here re-implements what those panels
 * already do — they keep their own queries, their own gating and their own internals.
 *
 * Friends is deliberately absent: an OOC trusted-partner list belongs to the account,
 * not to any one character, so it moved off the sheet entirely (`/settings`).
 */

import { Link } from 'react-router-dom';
import { AdvancementTab } from '@/progression/components/advancement/AdvancementTab';
import { AgreementsPanel } from '@/estates/components/AgreementsPanel';
import { CluesTab } from '@/clues/components/CluesTab';
import { CrimeTab } from '@/justice/components/CrimeTab';
import { DistinctionsTab } from '@/distinctions/components/DistinctionsTab';
import { GossipPanel } from '@/secrets/components/GossipPanel';
import { KinshipPanel } from '@/kinship/components/KinshipPanel';
import { LanguagesSection } from '@/character_sheets/components/LanguagesSection';
import { LocationsTab } from '@/locations/components/LocationsTab';
import { RelationshipsSection } from '@/components/character';
import { ReputationTab } from '@/reputation/components/ReputationTab';
import { SecretsTab } from '@/secrets/components/SecretsTab';
import { SpellbookTab } from '@/magic/components/SpellbookTab';
import { StaffSecretsPanel } from '@/secrets/components/StaffSecretsPanel';
import { TitlesPanel } from '@/achievements/components/TitlesPanel';
import { UpdatesTab } from '@/sheet_update_requests/components/UpdatesTab';
import { XpLedgerCard } from '@/progression/components/advancement/XpLedgerCard';
import { useCharacterPurse } from '@/status/queries';
import { useInventory } from '@/inventory/hooks/useInventory';
import { useOutfits } from '@/inventory/hooks/useOutfits';
import { useThreads } from '@/magic/queries';
import { formatCoppers } from '@/lib/currency';
import type { CharacterSheetMentor, CharacterSheetPayload } from '@/character_sheets/api';
import { Entries, Entry, Heading, Ledger, Stack, Tag } from './primitives';

/**
 * Ties — who they know, who they are to, and where they stand.
 *
 * Titles moved under the name on the plate, so what is left here is the standing rail:
 * organizations, reputation and the covenant role.
 */
export function TiesPanel({
  sheetId,
  entryId,
  isMyCharacter,
  viewerPersonaId,
  viewedPersonaId,
  titlesPersonaId,
  mentors,
}: {
  sheetId: number;
  entryId: number;
  isMyCharacter: boolean;
  viewerPersonaId: number | null;
  viewedPersonaId: number | null;
  titlesPersonaId: number | null;
  /** Active Mentor's Vow bonds; empty for anyone the payload did not give them to. */
  mentors: CharacterSheetMentor[];
}) {
  return (
    <div className="refsheet-columns-2">
      <Stack wide>
        <Stack>
          <Heading>Relationships</Heading>
          <RelationshipsSection characterSheetId={sheetId} isMyCharacter={isMyCharacter} />
        </Stack>
        <Stack>
          <Heading>Kin</Heading>
          <KinshipPanel characterId={sheetId} />
        </Stack>
        {mentors.length > 0 && (
          <Stack>
            <Heading>Mentors</Heading>
            <Ledger>Vows sworn inside a covenant, one way and the other.</Ledger>
            <Entries>
              {mentors.map((bond) => (
                <Entry
                  key={bond.id}
                  name={bond.name}
                  aside={<span className="refsheet-note">{bond.covenant}</span>}
                  tags={<Tag accent>{bond.role}</Tag>}
                />
              ))}
            </Entries>
          </Stack>
        )}
      </Stack>
      <Stack wide>
        <Stack>
          <Heading>Standing</Heading>
          <ReputationTab
            entryCharacterId={sheetId}
            viewerPersonaId={viewerPersonaId}
            isMyCharacter={isMyCharacter}
            viewedEntryId={entryId}
            viewedPersonaId={viewedPersonaId}
          />
        </Stack>
        <Stack>
          <Heading>Titles</Heading>
          <TitlesPanel personaId={titlesPersonaId} />
        </Stack>
      </Stack>
    </div>
  );
}

/** Distinctions — the full list; the server already filters secret rows by viewer. */
export function DistinctionsPanel({ sheetId }: { sheetId: number }) {
  return (
    <Stack>
      <Heading>Distinctions</Heading>
      <DistinctionsTab characterId={sheetId} />
    </Stack>
  );
}

/**
 * Magic — the spellbook, plus the character's threads and where each is anchored.
 *
 * The aura lives here, which is why Dan's ruling sent it off the plate: this is the page
 * a reader opens to see how someone's magic is faring. The section splits the way the
 * demo draws it — what a caster DOES down the main column, what their magic IS in the
 * rail — which `SpellbookTab`'s `slot` prop exists to serve. Threads are the owner's own
 * (the list endpoint is account-scoped), narrowed to THIS character by the `owner` filter
 * so an account with alts does not read another character's weaving here.
 */
export function MagicPanel({
  sheetId,
  isMyCharacter,
}: {
  sheetId: number;
  isMyCharacter: boolean;
}) {
  return (
    <div className="refsheet-columns-2">
      <Stack wide>
        <Stack>
          <Heading>Gifts</Heading>
          <SpellbookTab characterId={sheetId} isMyCharacter={isMyCharacter} slot="main" />
        </Stack>
        {isMyCharacter && <ThreadsBlock sheetId={sheetId} />}
      </Stack>
      {/* The rail holds what their magic IS, beside what they DO with it: the aura and
          the resonances they hold. Both halves read one payload through one cache key. */}
      <Stack wide>
        <SpellbookTab characterId={sheetId} isMyCharacter={isMyCharacter} slot="rail" />
      </Stack>
    </div>
  );
}

/** What the character has woven, and on what. Owner-only. */
function ThreadsBlock({ sheetId }: { sheetId: number }) {
  const { data } = useThreads({ characterSheetId: sheetId });
  const threads = data?.results ?? [];
  if (threads.length === 0) return null;
  return (
    <Stack>
      <Heading>Threads</Heading>
      <Ledger>What they have woven, and where.</Ledger>
      <Entries>
        {threads.map((thread) => (
          <Entry
            key={thread.id}
            name={thread.name || thread.target_kind}
            tags={
              <>
                <Tag>{thread.target_kind}</Tag>
                <Tag>Level {thread.level}</Tag>
                {thread.resonance_name && <Tag>{thread.resonance_name}</Tag>}
              </>
            }
            gloss={thread.description || undefined}
          />
        ))}
      </Entries>
      <p className="refsheet-note">
        Woven and imbued by ritual. Soul tethers are listed under Ties, since they are to a person.
      </p>
    </Stack>
  );
}

/** Knowledge — what they know and what they could tell. The player's own. */
export function KnowledgePanel({
  sheetId,
  viewerEntryId,
  isStaff,
}: {
  sheetId: number;
  viewerEntryId: number | null;
  isStaff: boolean;
}) {
  return (
    <div className="refsheet-columns-3">
      <Stack>
        <Heading>Secrets</Heading>
        <SecretsTab subjectId={sheetId} viewerId={viewerEntryId} />
        {isStaff && <StaffSecretsPanel subjectId={sheetId} />}
      </Stack>
      <Stack>
        <Heading>Clues</Heading>
        <CluesTab characterSheetId={sheetId} />
      </Stack>
      <Stack>
        <Heading>Gossip</Heading>
        <GossipPanel viewerId={viewerEntryId} />
      </Stack>
    </div>
  );
}

/**
 * Holdings — the purse, what they carry, where they live, what they have promised, and
 * whether the law wants them.
 *
 * Dan's merge: money, possessions and property are one question for a player ("what do
 * I have?"), and debts sit beside the coin that pays them rather than in a tab of their
 * own. What is WORN is on Physical instead, because it is visible.
 */
export function HoldingsPanel({
  sheetId,
  viewedPersonaId,
  isActiveCharacter,
  viewerEntryId,
}: {
  sheetId: number;
  viewedPersonaId: number | null;
  isActiveCharacter: boolean;
  viewerEntryId: number | null;
}) {
  const { data: purse } = useCharacterPurse(sheetId);

  return (
    <Stack wide>
      <div className="refsheet-columns-3">
        <Stack>
          <Heading>Purse</Heading>
          {/* The purse row lazy-creates at zero server-side, so a coinless character
              reads "0c" rather than an absent block; `purse` itself is null only when
              the endpoint refused the viewer. */}
          {purse ? (
            <p style={{ fontSize: '1.375rem' }}>{formatCoppers(purse.balance ?? 0)}</p>
          ) : (
            <Ledger>No purse to read.</Ledger>
          )}
          <p className="refsheet-note">
            Coin on hand. Loose caches and minted instruments are items, and travel with the rest of
            what they carry.
          </p>
        </Stack>
        <CarriedBlock sheetId={sheetId} />
        <Stack>
          <Heading>The law</Heading>
          <CrimeTab viewerEntryId={viewerEntryId} />
        </Stack>
      </div>
      <div className="refsheet-columns-even">
        <Stack>
          <Heading>Property</Heading>
          <LocationsTab personaId={viewedPersonaId} isActiveCharacter={isActiveCharacter} />
        </Stack>
        <Stack>
          <Heading>Agreements</Heading>
          <AgreementsPanel characterSheetId={sheetId} />
        </Stack>
      </div>
    </Stack>
  );
}

/**
 * What they carry: how much of it there is, the few pieces worth naming, and the outfits
 * they keep, each a door into the wardrobe where the sorting and the changing happen.
 *
 * "Notable" is read as worth: the most valuable handful. That is a judgement the sheet
 * has to make because the inventory has no notability flag, and value is the only signal
 * on the row that means anything to a reader.
 *
 * The worn outfit is NOT marked, and the demo marks it. `Outfit` carries no worn flag,
 * and inferring one would mean fetching every outfit's slots and comparing them to the
 * equipped set, which is a query per outfit for a marker. Recorded rather than guessed.
 */
function CarriedBlock({ sheetId }: { sheetId: number }) {
  const { data: inventory = [] } = useInventory(sheetId);
  const { data: outfits = [] } = useOutfits(sheetId);

  const notable = [...inventory]
    .sort((a, b) => (b.suggested_value ?? 0) - (a.suggested_value ?? 0))
    .slice(0, 4);

  return (
    <Stack>
      <Heading>Carried</Heading>
      <Ledger>
        {inventory.length === 0
          ? 'They carry nothing.'
          : `${inventory.length} ${inventory.length === 1 ? 'thing' : 'things'}, sorted in the `}
        {inventory.length > 0 && <Link to="/wardrobe">wardrobe</Link>}
        {inventory.length > 0 && '.'}
      </Ledger>
      {notable.length > 0 && (
        <Entries>
          {notable.map((item) => (
            <Entry
              key={item.id}
              name={item.display_name}
              tags={item.quality_tier?.name ? <Tag>{item.quality_tier.name}</Tag> : undefined}
            />
          ))}
        </Entries>
      )}
      {outfits.length > 0 && (
        <Stack>
          <Ledger>Outfits they keep.</Ledger>
          <Entries>
            {outfits.map((outfit) => (
              <Entry key={outfit.id} name={outfit.name} gloss={outfit.description || undefined} />
            ))}
          </Entries>
        </Stack>
      )}
      <Link className="refsheet-quiet-door" to="/wardrobe">
        Change outfit
      </Link>
    </Stack>
  );
}

/** Growth — spending, and changing the sheet. The player's own. */
export function GrowthPanel({
  sheetId,
  isMyCharacter,
  isActiveCharacter,
  originStoryEditor,
}: {
  sheetId: number;
  isMyCharacter: boolean;
  isActiveCharacter: boolean;
  /** The finish-later origin-story dialog, composed by the page that owns the payload. */
  originStoryEditor?: React.ReactNode;
}) {
  return (
    <div className="refsheet-columns-2">
      <Stack wide>
        <Stack>
          <Heading>Advancement</Heading>
          <XpLedgerCard sheetId={sheetId} />
          <AdvancementTab characterId={sheetId} isActiveCharacter={isActiveCharacter} />
        </Stack>
        <Stack>
          <Heading>Changes to the sheet</Heading>
          <UpdatesTab characterId={sheetId} isMyCharacter={isMyCharacter} />
        </Stack>
      </Stack>
      <Stack wide>
        <Stack>
          <Heading>Languages</Heading>
          <LanguagesSection />
        </Stack>
        {originStoryEditor && (
          <Stack>
            <Heading>Origin story</Heading>
            {originStoryEditor}
          </Stack>
        )}
      </Stack>
    </div>
  );
}

/** Convenience re-export so the page imports one module for every section. */
export type { CharacterSheetPayload };

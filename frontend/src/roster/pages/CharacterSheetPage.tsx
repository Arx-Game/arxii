import { Link, useParams } from 'react-router-dom';
import { useAppSelector, useAccount } from '@/store/hooks';
import { useRosterEntryQuery, useMyRosterEntriesQuery } from '../queries';
import { useOrganizationByName } from '@/orgs/queries';
import {
  CharacterPortrait,
  BackgroundSection,
  StatsSection,
  RelationshipsSection,
  GalleriesSection,
  ApplicationSlot,
} from '@/components/character';
import { MessagesSection } from '@/narrative/components/MessagesSection';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { ReputationTab } from '@/reputation/components/ReputationTab';
import { VitalsPanel } from '@/vitals/components/VitalsPanel';
import { FriendButton } from '@/friends/components/FriendButton';
import { RivalButton } from '@/friends/components/RivalButton';
import { FriendsTab } from '@/friends/components/FriendsTab';
import { GossipPanel } from '@/secrets/components/GossipPanel';
import { SecretsTab } from '@/secrets/components/SecretsTab';
import { CluesTab } from '@/clues/components/CluesTab';
import { CrimeTab } from '@/justice/components/CrimeTab';
import { TitlesPanel } from '@/achievements/components/TitlesPanel';
import { OriginStoryEditorDialog } from '@/character_sheets/components/OriginStoryEditorDialog';
import { useCharacterSheetQuery } from '@/character_sheets/queries';
import { DistinctionsTab } from '@/distinctions/components/DistinctionsTab';
import { UpdatesTab } from '@/sheet_update_requests/components/UpdatesTab';
import { SpellbookTab } from '@/magic/components/SpellbookTab';
import { LocationsTab } from '@/locations/components/LocationsTab';
import { AgreementsPanel } from '@/estates/components/AgreementsPanel';

export function CharacterSheetPage() {
  const { id } = useParams();
  const entryId = Number(id);
  const { data: entry, isLoading } = useRosterEntryQuery(entryId);
  const { data: myEntries } = useMyRosterEntriesQuery();
  const account = useAccount();

  // Show messages section only when the viewing user owns this character.
  const isMyCharacter = myEntries?.some((e) => e.id === entryId) ?? false;
  // Full character sheet payload — needed for the origin-story finish-later
  // editor (#2478) which reads story.origin_slots.
  const { data: sheetPayload } = useCharacterSheetQuery(entry?.character.id ?? 0);
  // For the Reputation tab on foreign sheets: resolve the viewer's primary
  // persona from their first owned character. Null when the viewer has
  // no characters → the backend returns the anonymous subset.
  const viewerPersonaId = myEntries?.[0]?.primary_persona_id ?? null;
  // For the Reputation tab's own-view: resolve the persona/entry of the character being
  // VIEWED (not the account's first-listed character) — an account can own several
  // characters, and scoping to myEntries[0] would leak another character's standing
  // (heat, org memberships/reputation) onto this sheet.
  const viewedMyEntry = myEntries?.find((e) => e.id === entryId);
  const viewedPersonaId = viewedMyEntry?.primary_persona_id ?? null;
  // For the Secrets tab: IC knowledge scopes to the ACTIVE character (never the account), so
  // resolve the active character's roster entry. Null when no character is active → no secrets.
  const activeCharacterName = useAppSelector((state) => state.game.active);
  const viewerEntryId = myEntries?.find((e) => e.name === activeCharacterName)?.id ?? null;
  // For the Locations tab's Ships section: GET /api/ships/ships/ is server-scoped to the
  // account's ACTIVE persona, not the character being viewed, so only render it when the
  // viewed character IS the active character (an account can own several characters).
  const isActiveCharacter = viewerEntryId === entryId;
  // Resolve a same-named org for the family click-through (#1446); membership-gated visibility
  // means an empty/absent result is normal — fall back to plain text in that case.
  const { data: familyOrg } = useOrganizationByName(entry?.character.family ?? '');

  if (isLoading) return <p className="p-4">Loading...</p>;
  if (!entry) return <p className="p-4">Character not found.</p>;

  const covenant = entry.character.covenant;
  const family = entry.character.family;

  return (
    <div className="container mx-auto space-y-4 p-4">
      <div className="space-y-2">
        <CharacterPortrait
          name={entry.fullname || entry.character.name}
          profilePicture={entry.profile_picture}
        >
          {covenant && (
            <p className="text-sm text-muted-foreground">
              <Link to={`/covenants/${covenant.id}`} className="hover:underline">
                {covenant.name}
              </Link>
              {' — '}
              {covenant.role}
            </p>
          )}
          {family && (
            <p className="text-sm text-muted-foreground">
              {familyOrg ? (
                <Link to={`/orgs/${familyOrg.id}`} className="hover:underline">
                  {family}
                </Link>
              ) : (
                family
              )}
            </p>
          )}
        </CharacterPortrait>
        {entry.quote && <blockquote className="italic">"{entry.quote}"</blockquote>}
        {/* Friend this character — an OOC trusted-partner designation (#1727), only on others' sheets. */}
        {!isMyCharacter && (
          <FriendButton
            viewerEntryId={viewerEntryId}
            targetEntryId={entryId}
            targetName={entry.character.name}
          />
        )}
        {/* Declare an IC rival — the antagonism-consent counterpart (#2170), double opt-in. */}
        {!isMyCharacter && (
          <RivalButton
            viewerEntryId={viewerEntryId}
            targetEntryId={entryId}
            targetName={entry.character.name}
          />
        )}
      </div>

      <Tabs defaultValue="sheet" className="space-y-4">
        <TabsList>
          <TabsTrigger value="sheet">Sheet</TabsTrigger>
          <TabsTrigger value="relationships">Relationships</TabsTrigger>
          <TabsTrigger value="reputation">Reputation</TabsTrigger>
          <TabsTrigger value="titles">Titles</TabsTrigger>
          <TabsTrigger value="distinctions">Distinctions</TabsTrigger>
          <TabsTrigger value="updates">Updates</TabsTrigger>
          <TabsTrigger value="magic">Magic</TabsTrigger>
          <TabsTrigger value="secrets">Secrets</TabsTrigger>
          {isMyCharacter && <TabsTrigger value="clues">Clues</TabsTrigger>}
          {isMyCharacter && <TabsTrigger value="gossip">Gossip</TabsTrigger>}
          {isMyCharacter && <TabsTrigger value="crime">Crime</TabsTrigger>}
          {isMyCharacter && <TabsTrigger value="friends">Friends</TabsTrigger>}
          {isMyCharacter && <TabsTrigger value="locations">Locations</TabsTrigger>}
          {isMyCharacter && <TabsTrigger value="agreements">Agreements</TabsTrigger>}
        </TabsList>

        <TabsContent value="sheet" className="space-y-4">
          <VitalsPanel characterId={entry.character.id} />
          {entry.description && (
            <section>
              <h3 className="text-xl font-semibold">Description</h3>
              <p>{entry.description}</p>
            </section>
          )}
          <BackgroundSection background={entry.character.background} />
          {isMyCharacter && sheetPayload && (
            <OriginStoryEditorDialog characterId={entry.character.id} sheet={sheetPayload} />
          )}
          <StatsSection
            age={entry.character.age}
            gender={entry.character.gender}
            race={entry.character.race}
            charClass={entry.character.char_class}
            level={entry.character.level}
            concept={entry.character.concept}
            family={entry.character.family}
            vocation={entry.character.vocation}
            socialRank={entry.character.social_rank}
          />
          <GalleriesSection galleries={entry.character.galleries} />
          <ApplicationSlot entry={entry} account={account} />
          {isMyCharacter && (
            <div id="messages">
              <MessagesSection />
            </div>
          )}
        </TabsContent>

        <TabsContent value="relationships" className="space-y-4">
          <RelationshipsSection
            characterSheetId={entry.character.id}
            isMyCharacter={isMyCharacter}
          />
        </TabsContent>

        <TabsContent value="reputation" className="space-y-4">
          {/* Consolidated Reputation tab (#1446): renown, standing (society + org), covenants,
              and wanted flags for the own view; the existing RenownCardPanel for foreign views.
              Radix unmounts inactive tab content, so these queries only fire when opened. */}
          <ReputationTab
            entryCharacterId={entry.character.id}
            viewerPersonaId={viewerPersonaId}
            isMyCharacter={isMyCharacter}
            viewedEntryId={entryId}
            viewedPersonaId={viewedPersonaId}
          />
        </TabsContent>

        <TabsContent value="titles" className="space-y-4">
          {/* Titles are cosmetic and public — render for any viewer. character.id is the
              CharacterSheet pk the titles API filters by. */}
          <TitlesPanel characterSheetId={entry.character.id} />
        </TabsContent>

        <TabsContent value="distinctions" className="space-y-4">
          {/* Ungated (#1446): the server already filters secret rows for non-privileged
              viewers, so every viewer sees this tab and the tab only renders what it's given.
              character.id is the CharacterSheet pk (shared with the ObjectDB pk). Radix
              unmounts inactive tab content, so the query only fires when this tab is opened. */}
          <DistinctionsTab characterId={entry.character.id} />
        </TabsContent>

        <TabsContent value="updates" className="space-y-4">
          {/* Ungated (#2631): the version-history endpoint gates true-profile history on
              reveal_identity server-side, so every viewer sees this tab; the submit form and
              request list render only for the owner. character.id is the CharacterSheet pk. */}
          <UpdatesTab characterId={entry.character.id} isMyCharacter={isMyCharacter} />
        </TabsContent>

        <TabsContent value="magic" className="space-y-4">
          {/* Ungated (#1446): the server already gates payload.magic to null for foreign
              viewers without visibility and for magic-less characters, so every viewer sees
              this tab and the tab only renders what it's given (a muted line when null).
              Spellbook/status view only — "the sheet describes; the scene does." character.id
              is the CharacterSheet pk. Radix unmounts inactive tab content, so the query only
              fires when this tab is opened. */}
          <SpellbookTab characterId={entry.character.id} isMyCharacter={isMyCharacter} />
        </TabsContent>

        <TabsContent value="secrets" className="space-y-4">
          {/* The character sheet shares its pk with the ObjectDB, so character.id is the
              CharacterSheet pk the secret-tab API filters by. Radix unmounts inactive tab
              content, so the query only fires when this tab is opened. */}
          <SecretsTab subjectId={entry.character.id} viewerId={viewerEntryId} />
        </TabsContent>

        {isMyCharacter && (
          <TabsContent value="clues" className="space-y-4">
            {/* Held clues are private — only your own character's journal. character.id is the
                CharacterSheet pk the clues API filters by. Radix unmounts inactive tab content,
                so the query only fires when this tab is opened. */}
            <CluesTab characterSheetId={entry.character.id} />
          </TabsContent>
        )}

        {isMyCharacter && (
          <TabsContent value="gossip" className="space-y-4">
            {/* Gossip is the active character's own spreadable Level-1 secrets, location-bound to a
                social hub (#1572) — so it's a self-only tab keyed on the active RosterEntry, not the
                viewed subject. Radix unmounts inactive tabs, so the query only fires when opened. */}
            <GossipPanel viewerId={viewerEntryId} />
          </TabsContent>
        )}

        {isMyCharacter && (
          <TabsContent value="crime" className="space-y-4">
            {/* Where your active persona is wanted (#1765) — self-only risk information keyed on
                the active RosterEntry, like Gossip. Radix unmounts inactive tabs, so the query
                only fires when opened. */}
            <CrimeTab viewerEntryId={viewerEntryId} />
          </TabsContent>
        )}

        {isMyCharacter && (
          <TabsContent value="friends" className="space-y-4">
            {/* Your OOC friends list (#1727) — account-wide trusted partners, separate from IC
                relationships. Add friends from other characters' sheets; this lists + removes. */}
            <FriendsTab />
          </TabsContent>
        )}

        {isMyCharacter && (
          <TabsContent value="locations" className="space-y-4">
            {/* Consolidated Locations tab (#1446): dwellings, tenancies, and ships. Own-only —
                dwellings/tenancies are keyed on the viewed character's persona (never the
                account's first-listed character, to avoid alt-leak); ships are self-scoped
                server-side to the requester's ACTIVE persona, so isActiveCharacter gates
                that section off when viewing a non-active character owned by this account.
                Radix unmounts inactive tabs, so these queries only fire when opened. */}
            <LocationsTab personaId={viewedPersonaId} isActiveCharacter={isActiveCharacter} />
          </TabsContent>
        )}

        {isMyCharacter && (
          <TabsContent value="agreements" className="space-y-4">
            {/* Agreements hub (#1985): binding declarations that fire later. V1 content is
                the will (bequests, executors, testament) plus executor/claim surfaces;
                vows, oaths, treaties, and pacts join as they ship. Sheet pk == character
                ObjectDB pk (OneToOne shares pk). */}
            <AgreementsPanel characterSheetId={entry.character.id} />
          </TabsContent>
        )}
      </Tabs>
    </div>
  );
}

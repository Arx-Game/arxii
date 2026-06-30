import { useParams } from 'react-router-dom';
import { useAppSelector } from '@/store/hooks';
import { useRosterEntryQuery, useMyRosterEntriesQuery } from '../queries';
import {
  CharacterPortrait,
  BackgroundSection,
  StatsSection,
  RelationshipsSection,
  GalleriesSection,
  CharacterApplicationForm,
} from '@/components/character';
import { MessagesSection } from '@/narrative/components/MessagesSection';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { RenownPanel } from '@/renown/components/RenownPanel';
import { RenownCardPanel } from '@/renown/components/RenownCardPanel';
import { VitalsPanel } from '@/vitals/components/VitalsPanel';
import { GossipPanel } from '@/secrets/components/GossipPanel';
import { SecretsTab } from '@/secrets/components/SecretsTab';
import { CluesTab } from '@/clues/components/CluesTab';
import { TitlesPanel } from '@/achievements/components/TitlesPanel';

export function CharacterSheetPage() {
  const { id } = useParams();
  const entryId = Number(id);
  const { data: entry, isLoading } = useRosterEntryQuery(entryId);
  const { data: myEntries } = useMyRosterEntriesQuery();

  // Show messages section only when the viewing user owns this character.
  const isMyCharacter = myEntries?.some((e) => e.id === entryId) ?? false;
  // For the Renown tab on foreign sheets: resolve the viewer's primary
  // persona from their first owned character. Null when the viewer has
  // no characters → the backend returns the anonymous subset.
  const viewerPersonaId = myEntries?.[0]?.primary_persona_id ?? null;
  // For the Secrets tab: IC knowledge scopes to the ACTIVE character (never the account), so
  // resolve the active character's roster entry. Null when no character is active → no secrets.
  const activeCharacterName = useAppSelector((state) => state.game.active);
  const viewerEntryId = myEntries?.find((e) => e.name === activeCharacterName)?.id ?? null;

  if (isLoading) return <p className="p-4">Loading...</p>;
  if (!entry) return <p className="p-4">Character not found.</p>;

  return (
    <div className="container mx-auto space-y-4 p-4">
      <div className="space-y-2">
        <CharacterPortrait
          name={entry.fullname || entry.character.name}
          profilePicture={entry.profile_picture}
        />
        {entry.quote && <blockquote className="italic">"{entry.quote}"</blockquote>}
      </div>

      <Tabs defaultValue="sheet" className="space-y-4">
        <TabsList>
          <TabsTrigger value="sheet">Sheet</TabsTrigger>
          <TabsTrigger value="relationships">Relationships</TabsTrigger>
          <TabsTrigger value="renown">Renown</TabsTrigger>
          <TabsTrigger value="titles">Titles</TabsTrigger>
          <TabsTrigger value="secrets">Secrets</TabsTrigger>
          {isMyCharacter && <TabsTrigger value="clues">Clues</TabsTrigger>}
          {isMyCharacter && <TabsTrigger value="gossip">Gossip</TabsTrigger>}
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
          {entry.can_apply && <CharacterApplicationForm entryId={entry.id} />}
          {isMyCharacter && (
            <div id="messages">
              <MessagesSection />
            </div>
          )}
        </TabsContent>

        <TabsContent value="relationships" className="space-y-4">
          <RelationshipsSection
            relationships={entry.character.relationships}
            characterSheetId={entry.character.id}
          />
        </TabsContent>

        <TabsContent value="renown" className="space-y-4">
          {isMyCharacter ? (
            <RenownPanel characterSheetId={entry.character.id} />
          ) : (
            <RenownCardPanel
              characterSheetId={entry.character.id}
              viewerPersonaId={viewerPersonaId}
            />
          )}
        </TabsContent>

        <TabsContent value="titles" className="space-y-4">
          {/* Titles are cosmetic and public — render for any viewer. character.id is the
              CharacterSheet pk the titles API filters by. */}
          <TitlesPanel characterSheetId={entry.character.id} />
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
      </Tabs>
    </div>
  );
}

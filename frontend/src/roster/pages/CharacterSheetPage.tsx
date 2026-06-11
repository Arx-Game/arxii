import { useParams } from 'react-router-dom';
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
          <TabsTrigger value="renown">Renown</TabsTrigger>
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
          <RelationshipsSection
            relationships={entry.character.relationships}
            characterSheetId={entry.character.id}
          />
          <GalleriesSection galleries={entry.character.galleries} />
          {entry.can_apply && <CharacterApplicationForm entryId={entry.id} />}
          {isMyCharacter && (
            <div id="messages">
              <MessagesSection />
            </div>
          )}
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
      </Tabs>
    </div>
  );
}

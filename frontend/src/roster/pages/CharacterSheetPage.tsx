import { useParams } from 'react-router-dom';
import { useRosterEntryQuery } from '../queries';
import {
  CharacterPortrait,
  BackgroundSection,
  StatsSection,
  RelationshipsSection,
  GalleriesSection,
  CharacterApplicationForm,
} from '../../components/character';

export function CharacterSheetPage() {
  const { id } = useParams();
  const entryId = Number(id);
  const { data: entry, isLoading } = useRosterEntryQuery(entryId);

  if (isLoading) return <p className="p-4">Loading...</p>;
  if (!entry) return <p className="p-4">Character not found.</p>;

  return (
    <div className="container mx-auto space-y-4 p-4">
      <CharacterPortrait name={entry.character.name} profilePicture={entry.profile_picture} />
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
      <RelationshipsSection relationships={entry.character.relationships} />
      <GalleriesSection galleries={entry.character.galleries} />
      {entry.can_apply && <CharacterApplicationForm entryId={entry.id} />}
    </div>
  );
}

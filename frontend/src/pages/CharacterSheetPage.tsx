import { useParams } from 'react-router-dom';
import { useRosterEntryQuery } from '../evennia_replacements/queries';
import {
  CharacterPortrait,
  BackgroundSection,
  StatsSection,
  RelationshipsSection,
  GalleriesSection,
  CharacterApplicationForm,
} from '../components/character';

export function CharacterSheetPage() {
  const { id } = useParams();
  const entryId = Number(id);
  const { data: entry, isLoading, error } = useRosterEntryQuery(entryId);

  if (isLoading) return <p className="p-4">Loading...</p>;
  if (error || !entry) return <p className="p-4">Character not found.</p>;

  return (
    <div className="container mx-auto space-y-4 p-4">
      <CharacterPortrait character={entry.character} />
      <BackgroundSection background={entry.character.background} />
      <StatsSection stats={entry.character.stats} />
      <RelationshipsSection relationships={entry.character.relationships} />
      <GalleriesSection galleries={entry.character.galleries} />
      {entry.can_apply && <CharacterApplicationForm entryId={entry.id} />}
    </div>
  );
}

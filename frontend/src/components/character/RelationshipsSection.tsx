import type { CharacterData } from '../../roster/types';

interface RelationshipsSectionProps {
  relationships?: CharacterData['relationships'];
}

export function RelationshipsSection({ relationships }: RelationshipsSectionProps) {
  return (
    <section>
      <h3 className="text-xl font-semibold">Relationships</h3>
      <ul className="list-disc pl-5">
        {relationships?.length ? (
          relationships.map((rel) => <li key={rel}>{rel}</li>)
        ) : (
          <li>TBD</li>
        )}
      </ul>
    </section>
  );
}

import type { CharacterData } from '../../roster/types';

interface StatsSectionProps {
  age?: CharacterData['age'];
  gender?: CharacterData['gender'];
  race?: CharacterData['race'];
  charClass?: CharacterData['char_class'];
  level?: CharacterData['level'];
  concept?: CharacterData['concept'];
  family?: CharacterData['family'];
  vocation?: CharacterData['vocation'];
  socialRank?: CharacterData['social_rank'];
}

export function StatsSection({
  age,
  gender,
  race,
  charClass,
  level,
  concept,
  family,
  vocation,
  socialRank,
}: StatsSectionProps) {
  return (
    <section>
      <h3 className="text-xl font-semibold">Stats</h3>
      <dl className="grid grid-cols-2 gap-x-2">
        <dt>Age</dt>
        <dd>{age ?? 'TBD'}</dd>
        <dt>Gender</dt>
        <dd>{gender ?? 'TBD'}</dd>
        <dt>Race</dt>
        <dd>
          {race?.race?.name
            ? `${race.race.name}${race.subrace ? ` (${race.subrace.name})` : ''}`
            : 'TBD'}
        </dd>
        <dt>Class</dt>
        <dd>{charClass ?? 'TBD'}</dd>
        <dt>Level</dt>
        <dd>{level ?? 'TBD'}</dd>
        <dt>Concept</dt>
        <dd>{concept || 'TBD'}</dd>
        <dt>Family</dt>
        <dd>{family || 'TBD'}</dd>
        <dt>Vocation</dt>
        <dd>{vocation || 'TBD'}</dd>
        <dt>Social Rank</dt>
        <dd>{socialRank ?? 'TBD'}</dd>
      </dl>
    </section>
  );
}

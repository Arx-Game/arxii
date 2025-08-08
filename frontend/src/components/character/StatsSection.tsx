import type { CharacterData } from '../../roster/types';

interface StatsSectionProps {
  stats?: CharacterData['stats'];
}

export function StatsSection({ stats }: StatsSectionProps) {
  return (
    <section>
      <h3 className="text-xl font-semibold">Stats</h3>
      <p>{stats ? JSON.stringify(stats) : 'TBD'}</p>
    </section>
  );
}

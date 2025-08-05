interface StatsSectionProps {
  stats?: Record<string, number>;
}

export function StatsSection({ stats }: StatsSectionProps) {
  return (
    <section>
      <h3 className="text-xl font-semibold">Stats</h3>
      <p>{stats ? JSON.stringify(stats) : 'TBD'}</p>
    </section>
  );
}

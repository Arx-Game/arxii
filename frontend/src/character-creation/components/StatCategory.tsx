/**
 * Stat Category Component
 *
 * Groups stats by category (Physical, Social, Mental, Defensive)
 * and renders StatSlider for each stat in the category.
 */

import { StatSlider } from './StatSlider';

interface StatCategoryProps {
  title: string;
  stats: string[];
  values: Record<string, number>;
  onChange: (statName: string, newValue: number) => void;
}

export function StatCategory({ title, stats, values, onChange }: StatCategoryProps) {
  return (
    <div className="space-y-3">
      <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
        {title}
      </h3>
      <div className="space-y-2">
        {stats.map((stat) => (
          <StatSlider
            key={stat}
            name={stat}
            value={values[stat] / 10} // Convert internal (10-50) to display (1-5)
            onChange={(val) => onChange(stat, val)}
          />
        ))}
      </div>
    </div>
  );
}

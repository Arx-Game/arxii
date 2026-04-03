/**
 * Stage 6: Attributes Allocation
 *
 * 12 primary statistics in 4 categories, allocated with a point budget.
 * Values are 1-5 directly (no internal scaling).
 */

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { motion } from 'framer-motion';
import { Loader2 } from 'lucide-react';
import { useMemo, useState } from 'react';
import { useCGExplanations, useStatDefinitions, useUpdateDraft } from '../queries';
import { getDefaultStats } from '../types';
import type { CharacterDraft, Stats } from '../types';
import { FreePointsWidget } from './FreePointsWidget';
import { StatCard } from './StatCard';
import { StatModal } from './StatModal';

interface AttributesStageProps {
  draft: CharacterDraft;
}

/** Stat categories with display labels and member stats. */
const STAT_CATEGORIES: { label: string; stats: (keyof Stats)[] }[] = [
  { label: 'Physical', stats: ['strength', 'agility', 'stamina'] },
  { label: 'Social', stats: ['charm', 'presence', 'composure'] },
  { label: 'Mental', stats: ['intellect', 'wits', 'stability'] },
  { label: 'Meta', stats: ['luck', 'perception', 'willpower'] },
];

export function AttributesStage({ draft }: AttributesStageProps) {
  const updateDraft = useUpdateDraft();
  const { data: copy } = useCGExplanations();
  const { data: statDefinitions, isLoading: statsLoading } = useStatDefinitions();
  const stats: Stats = draft.draft_data.stats ?? getDefaultStats();
  const pointsRemaining = draft.stats_points_remaining;
  const budget = draft.stats_budget;
  const statBonuses = draft.stat_bonuses ?? {};

  // State for hover (desktop) and tap (mobile) interactions
  const [hoveredStat, setHoveredStat] = useState<string | null>(null);
  const [selectedStat, setSelectedStat] = useState<string | null>(null);

  // Build a map of stat name -> description from API data
  const statDescriptions = useMemo(() => {
    if (!statDefinitions) return {};
    return Object.fromEntries(statDefinitions.map((s) => [s.name, s.description]));
  }, [statDefinitions]);

  const handleStatChange = (statName: string, newValue: number) => {
    updateDraft.mutate({
      draftId: draft.id,
      data: {
        draft_data: {
          ...draft.draft_data,
          stats: {
            ...stats,
            [statName]: newValue,
          },
        },
      },
    });
  };

  if (statsLoading) {
    return (
      <div className="flex items-center justify-center py-8">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <>
      <div className="grid gap-8 lg:grid-cols-[1fr_300px]">
        {/* Main content */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -20 }}
          transition={{ duration: 0.3 }}
          className="space-y-8"
        >
          {/* Header section */}
          <div>
            <h2 className="theme-heading text-2xl font-bold">{copy?.attributes_heading ?? ''}</h2>
            <p className="mt-2 text-muted-foreground">{copy?.attributes_intro ?? ''}</p>
          </div>

          {/* Stats grouped by category */}
          <div className="space-y-6">
            {STAT_CATEGORIES.map((category) => (
              <div key={category.label}>
                <h3 className="mb-3 text-sm font-semibold uppercase tracking-wider text-muted-foreground">
                  {category.label}
                </h3>
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
                  {category.stats.map((stat) => {
                    const allocated = stats[stat];
                    const bonus = statBonuses[stat] || 0;
                    return (
                      <StatCard
                        key={stat}
                        name={stat}
                        value={allocated}
                        bonus={bonus !== 0 ? bonus : undefined}
                        onChange={(val) => handleStatChange(stat, val)}
                        onHover={setHoveredStat}
                        onTap={() => setSelectedStat(stat)}
                        canDecrease={allocated > 1}
                        canIncrease={allocated < 5 && pointsRemaining > 0}
                      />
                    );
                  })}
                </div>
              </div>
            ))}
          </div>

          {/* Points warning (if over/under) */}
          {pointsRemaining !== 0 && (
            <div className="rounded-md border border-amber-500/50 bg-amber-500/10 p-4">
              <p className="text-sm text-amber-600 dark:text-amber-400">
                {pointsRemaining > 0
                  ? `You have ${pointsRemaining} unspent points. Continue or spend them here.`
                  : `You are ${Math.abs(pointsRemaining)} points over budget. Lower some stats.`}
              </p>
            </div>
          )}
        </motion.div>

        {/* Sidebar - desktop only */}
        <div className="hidden lg:block">
          <div className="sticky top-4 space-y-4">
            <FreePointsWidget pointsRemaining={pointsRemaining} budget={budget} />
            {hoveredStat && (
              <Card>
                <CardHeader>
                  <CardTitle className="capitalize">{hoveredStat}</CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-sm text-muted-foreground">
                    {statDescriptions[hoveredStat] || ''}
                  </p>
                </CardContent>
              </Card>
            )}
          </div>
        </div>
      </div>

      {/* Mobile modal */}
      <StatModal
        stat={
          selectedStat
            ? { name: selectedStat, description: statDescriptions[selectedStat] || '' }
            : null
        }
        onClose={() => setSelectedStat(null)}
      />
    </>
  );
}

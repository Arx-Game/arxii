/**
 * Stage 4: Attributes Allocation
 *
 * Primary statistics allocation with point management.
 * Players start with 2 in each stat (18 points) plus 5 free points to distribute.
 */

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { motion } from 'framer-motion';
import { Loader2 } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { useStatDefinitions, useUpdateDraft } from '../queries';
import { calculateFreePoints, getDefaultStats } from '../types';
import type { CharacterDraft, Stats } from '../types';
import { FreePointsWidget } from './FreePointsWidget';
import { StatCard } from './StatCard';
import { StatModal } from './StatModal';

interface AttributesStageProps {
  draft: CharacterDraft;
}

/** All stats in display order */
const STAT_ORDER: (keyof Stats)[] = [
  'strength',
  'agility',
  'stamina',
  'charm',
  'presence',
  'perception',
  'intellect',
  'wits',
  'willpower',
];

export function AttributesStage({ draft }: AttributesStageProps) {
  const updateDraft = useUpdateDraft();
  const { data: statDefinitions, isLoading: statsLoading } = useStatDefinitions();
  const stats: Stats = draft.draft_data.stats ?? getDefaultStats();
  const freePoints = calculateFreePoints(stats);
  const isComplete = freePoints === 0;

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
            [statName]: newValue * 10, // Convert display (1-5) to internal (10-50)
          },
        },
      },
    });
  };

  // Auto-update completion status
  useEffect(() => {
    const currentComplete = draft.draft_data.attributes_complete;
    if (currentComplete !== isComplete) {
      updateDraft.mutate({
        draftId: draft.id,
        data: {
          draft_data: {
            ...draft.draft_data,
            attributes_complete: isComplete,
          },
        },
      });
    }
  }, [isComplete, draft.id, draft.draft_data, updateDraft]);

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
            <h2 className="text-2xl font-bold">Primary Attributes</h2>
            <p className="mt-2 text-muted-foreground">
              Allocate your character's primary statistics. Start with 2 in each stat, plus 5 free
              points to distribute.
            </p>
          </div>

          {/* 3x3 stat grid */}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 md:grid-cols-3">
            {STAT_ORDER.map((stat) => (
              <StatCard
                key={stat}
                name={stat}
                description={statDescriptions[stat]}
                value={Math.floor(stats[stat] / 10)}
                onChange={(val) => handleStatChange(stat, val)}
                onHover={setHoveredStat}
                onTap={() => setSelectedStat(stat)}
                canDecrease={Math.floor(stats[stat] / 10) > 1}
                canIncrease={Math.floor(stats[stat] / 10) < 5 && freePoints > 0}
              />
            ))}
          </div>

          {/* Points warning (if over/under) */}
          {freePoints !== 0 && (
            <div className="rounded-md border border-amber-500/50 bg-amber-500/10 p-4">
              <p className="text-sm text-amber-600 dark:text-amber-400">
                {freePoints > 0
                  ? `You have ${freePoints} unspent points. Continue or spend them here.`
                  : `You are ${Math.abs(freePoints)} points over budget. Lower some stats.`}
              </p>
            </div>
          )}
        </motion.div>

        {/* Sidebar - desktop only */}
        <div className="hidden lg:block">
          <div className="sticky top-4 space-y-4">
            <FreePointsWidget freePoints={freePoints} />
            {hoveredStat && (
              <Card>
                <CardHeader>
                  <CardTitle className="capitalize">{hoveredStat}</CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-sm text-muted-foreground">{statDescriptions[hoveredStat]}</p>
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

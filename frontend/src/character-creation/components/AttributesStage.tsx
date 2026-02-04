/**
 * Stage 4: Attributes Allocation
 *
 * Primary statistics allocation with point management.
 * Players start with 2 in each stat (18 points) plus 5 free points to distribute.
 */

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { motion } from 'framer-motion';
import { AlertCircle, Check, Loader2 } from 'lucide-react';
import { useEffect, useMemo } from 'react';
import { useStatDefinitions, useUpdateDraft } from '../queries';
import { calculateFreePoints, getDefaultStats } from '../types';
import type { CharacterDraft, Stats } from '../types';
import { StatSlider } from './StatSlider';

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
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -20 }}
      transition={{ duration: 0.3 }}
      className="space-y-8"
    >
      <div>
        <h2 className="text-2xl font-bold">Primary Attributes</h2>
        <p className="mt-2 text-muted-foreground">
          Allocate your character's primary statistics. Start with 2 in each stat, plus 5 free
          points to distribute.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center justify-between">
            <span>Stat Allocation</span>
            <div
              className={`flex items-center gap-2 ${
                freePoints === 0 ? 'text-green-600' : freePoints < 0 ? 'text-red-600' : ''
              }`}
            >
              {freePoints === 0 && <Check className="h-5 w-5" />}
              {freePoints < 0 && <AlertCircle className="h-5 w-5" />}
              <span>Free Points: {freePoints}</span>
            </div>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {STAT_ORDER.map((stat) => (
            <StatSlider
              key={stat}
              name={stat}
              description={statDescriptions[stat]}
              value={Math.floor(stats[stat] / 10)}
              onChange={(val) => handleStatChange(stat, val)}
            />
          ))}

          {freePoints !== 0 && (
            <div className="mt-4 rounded-md border border-amber-500/50 bg-amber-500/10 p-4">
              <p className="text-sm text-amber-600 dark:text-amber-400">
                {freePoints > 0
                  ? `You have ${freePoints} unspent points. Continue or spend them here.`
                  : `You are ${Math.abs(freePoints)} points over budget. Lower some stats.`}
              </p>
            </div>
          )}
        </CardContent>
      </Card>
    </motion.div>
  );
}

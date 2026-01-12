/**
 * Stage 1: Origin Selection
 *
 * Starting area selection with visual card grid.
 */

import { motion } from 'framer-motion';
import { useStartingAreas, useUpdateDraft } from '../queries';
import type { CharacterDraft, StartingArea } from '../types';
import { StartingAreaCard } from './StartingAreaCard';

interface OriginStageProps {
  draft: CharacterDraft;
}

export function OriginStage({ draft }: OriginStageProps) {
  const { data: areas, isLoading, error } = useStartingAreas();
  const updateDraft = useUpdateDraft();

  const handleSelectArea = (area: StartingArea) => {
    // If changing area, clear heritage and species since they depend on area
    const shouldClearDependents = draft.selected_area?.id !== area.id;

    updateDraft.mutate({
      draftId: draft.id,
      data: {
        selected_area_id: area.id,
        ...(shouldClearDependents && {
          selected_heritage_id: null,
          species: '',
          family_id: null,
        }),
      },
    });
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-lg border border-destructive bg-destructive/10 p-4 text-destructive">
        Failed to load starting areas. Please try again.
      </div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -20 }}
      transition={{ duration: 0.3 }}
    >
      <div className="mb-6">
        <h2 className="text-2xl font-bold">Choose Your Origin</h2>
        <p className="mt-2 text-muted-foreground">
          Select the city or region where your character's story begins. This choice will determine
          available heritage options, species, and families.
        </p>
      </div>

      <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
        {areas?.map((area) => (
          <StartingAreaCard
            key={area.id}
            area={area}
            isSelected={draft.selected_area?.id === area.id}
            onSelect={handleSelectArea}
          />
        ))}
      </div>

      {areas?.length === 0 && (
        <div className="rounded-lg border border-dashed p-8 text-center text-muted-foreground">
          No starting areas are currently available.
        </div>
      )}
    </motion.div>
  );
}

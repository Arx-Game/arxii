/**
 * Stage 1: Origin Selection
 *
 * Starting area selection with master-detail layout.
 * Left side shows condensed area cards, right side shows
 * an animated detail panel with the area's full description.
 */

import { useRealmTheme } from '@/components/realm-theme-provider';
import { Card, CardContent } from '@/components/ui/card';
import { AnimatePresence, motion } from 'framer-motion';
import { CheckCircle2 } from 'lucide-react';
import { useEffect, useState } from 'react';

import { useStartingAreas, useUpdateDraft } from '../queries';
import type { CharacterDraft, StartingArea } from '../types';
import { getRealmTheme } from '../utils';
import { getGradientColors, StartingAreaCard } from './StartingAreaCard';

interface OriginStageProps {
  draft: CharacterDraft;
}

export function OriginStage({ draft }: OriginStageProps) {
  const { data: areas, isLoading, error } = useStartingAreas();
  const updateDraft = useUpdateDraft();
  const { setRealmTheme } = useRealmTheme();
  const [hoveredArea, setHoveredArea] = useState<StartingArea | null>(null);

  const detailArea = hoveredArea ?? draft.selected_area ?? areas?.[0] ?? null;

  // Set theme based on currently selected area when component mounts
  useEffect(() => {
    if (draft.selected_area) {
      setRealmTheme(getRealmTheme(draft.selected_area.name));
    }
  }, [draft.selected_area, setRealmTheme]);

  const handleSelectArea = (area: StartingArea) => {
    setRealmTheme(getRealmTheme(area.name));
    // If changing area, clear heritage and species since they depend on area
    const shouldClearDependents = draft.selected_area?.id !== area.id;

    updateDraft.mutate({
      draftId: draft.id,
      data: {
        selected_area_id: area.id,
        ...(shouldClearDependents && {
          selected_beginnings_id: null,
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
        <h2 className="theme-heading text-2xl font-bold">Choose Your Origin</h2>
        <p className="mt-2 text-muted-foreground">
          Select the city or region where your character's story begins. This choice will determine
          available heritage options, species, and families.
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_1fr]">
        {/* Left: Area cards */}
        <div className="grid gap-4 sm:grid-cols-2">
          {areas?.map((area) => (
            <StartingAreaCard
              key={area.id}
              area={area}
              isSelected={draft.selected_area?.id === area.id}
              isHighlighted={detailArea?.id === area.id}
              onSelect={handleSelectArea}
              onHover={setHoveredArea}
            />
          ))}
        </div>

        {/* Right: Detail panel (desktop only) */}
        {detailArea && (
          <div className="hidden lg:block">
            <AreaDetailPanel
              area={detailArea}
              isSelected={draft.selected_area?.id === detailArea.id}
            />
          </div>
        )}
      </div>

      {/* Mobile: Detail panel below cards */}
      {detailArea && (
        <div className="mt-6 lg:hidden">
          <AreaDetailPanel
            area={detailArea}
            isSelected={draft.selected_area?.id === detailArea.id}
          />
        </div>
      )}

      {areas?.length === 0 && (
        <div className="rounded-lg border border-dashed p-8 text-center text-muted-foreground">
          No starting areas are currently available.
        </div>
      )}
    </motion.div>
  );
}

function AreaDetailPanel({ area, isSelected }: { area: StartingArea; isSelected: boolean }) {
  const [color1, color2] = getGradientColors(area.name);

  return (
    <AnimatePresence mode="wait">
      <motion.div
        key={area.id}
        initial={{ opacity: 0, x: 10 }}
        animate={{ opacity: 1, x: 0 }}
        exit={{ opacity: 0, x: -10 }}
        transition={{ duration: 0.25 }}
        className="sticky top-4"
      >
        <Card className="overflow-hidden">
          {/* Gradient header */}
          <div
            className="relative flex h-32 items-end p-6"
            style={{
              background: area.crest_image
                ? `url(${area.crest_image}) center/cover`
                : `linear-gradient(135deg, ${color1}, ${color2})`,
            }}
          >
            <div className="absolute inset-0 bg-gradient-to-t from-black/60 to-transparent" />
            <h3 className="theme-heading relative text-2xl font-bold text-white drop-shadow-lg">
              {area.name}
            </h3>
            {isSelected && (
              <CheckCircle2 className="relative ml-auto h-6 w-6 text-white drop-shadow-lg" />
            )}
          </div>
          <CardContent className="p-6">
            <p className="whitespace-pre-wrap leading-relaxed text-muted-foreground">
              {area.description}
            </p>
            {!area.is_accessible && (
              <p className="mt-4 text-sm text-destructive">
                This area is not currently accessible to your account.
              </p>
            )}
          </CardContent>
        </Card>
      </motion.div>
    </AnimatePresence>
  );
}

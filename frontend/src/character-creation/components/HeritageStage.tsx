/**
 * Stage 2: Heritage Selection
 *
 * Handles:
 * - Beginnings selection (worldbuilding path)
 * - Species selection (gated by Beginnings' allowed_species)
 * - Gender selection (3 options)
 *
 * Family selection has moved to LineageStage (Stage 3).
 * Pronouns are auto-derived at finalization.
 * Age is set in AppearanceStage.
 */

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { cn } from '@/lib/utils';
import { AnimatePresence, motion } from 'framer-motion';
import { CheckCircle2 } from 'lucide-react';
import { useState } from 'react';

import {
  useBeginnings,
  useCGExplanations,
  useCGPointBudget,
  useGenders,
  useSpecies,
  useUpdateDraft,
} from '../queries';
import type { Beginnings, CharacterDraft, GenderOption, Species } from '../types';
import { Stage } from '../types';
import { CGPointsWidget } from './CGPointsWidget';
import { SpeciesCard } from './SpeciesCard';
import { getGradientColors } from './StartingAreaCard';
import { StatBonusBadges } from './StatBonusBadges';

interface HeritageStageProps {
  draft: CharacterDraft;
  onStageSelect: (stage: Stage) => void;
}

export function HeritageStage({ draft, onStageSelect }: HeritageStageProps) {
  const updateDraft = useUpdateDraft();
  const { data: copy } = useCGExplanations();
  const [hoveredBeginnings, setHoveredBeginnings] = useState<Beginnings | null>(null);
  const [hoveredSpecies, setHoveredSpecies] = useState<Species | null>(null);

  // Fetch CG budget, beginnings, species, and genders
  const { data: cgBudget } = useCGPointBudget();
  const { data: beginnings, isLoading: beginningsLoading } = useBeginnings(draft.selected_area?.id);
  const { data: allSpecies, isLoading: speciesLoading } = useSpecies();
  const { data: genders, isLoading: gendersLoading } = useGenders();

  const detailBeginnings =
    hoveredBeginnings ?? draft.selected_beginnings ?? beginnings?.[0] ?? null;

  // If no area selected, prompt user to go back
  if (!draft.selected_area) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="py-12 text-center"
      >
        <p className="mb-4 text-muted-foreground">Please select a starting area first.</p>
        <Button onClick={() => onStageSelect(Stage.ORIGIN)}>Go to Origin Selection</Button>
      </motion.div>
    );
  }

  const handleBeginningsSelect = (beginningsOption: Beginnings) => {
    updateDraft.mutate({
      draftId: draft.id,
      data: {
        selected_beginnings_id: beginningsOption.id,
        // Clear species when changing beginnings
        selected_species_id: null,
      },
    });
  };

  const handleSpeciesSelect = (speciesId: number) => {
    updateDraft.mutate({
      draftId: draft.id,
      data: {
        selected_species_id: speciesId,
      },
    });
  };

  const handleGenderChange = (gender: GenderOption) => {
    updateDraft.mutate({
      draftId: draft.id,
      data: {
        selected_gender_id: gender.id,
      },
    });
  };

  // Filter species based on selected beginnings' allowed_species_ids
  const filteredSpecies = allSpecies?.filter((species) => {
    if (!draft.selected_beginnings) return false;
    return draft.selected_beginnings.allowed_species_ids.includes(species.id);
  });

  // Calculate CG points
  const startingPoints = cgBudget?.starting_points ?? 100;
  const spentPoints = draft.cg_points_spent ?? 0;
  const remainingPoints = draft.cg_points_remaining ?? startingPoints;

  return (
    <div className="grid gap-8 lg:grid-cols-[1fr_300px]">
      {/* Main Content */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -20 }}
        transition={{ duration: 0.3 }}
        className="space-y-8"
      >
        <div>
          <h2 className="theme-heading text-2xl font-bold">{copy?.heritage_heading ?? ''}</h2>
          <p className="mt-2 text-muted-foreground">{copy?.heritage_intro ?? ''}</p>
        </div>

        {/* Beginnings Selection */}
        <section className="space-y-4">
          <div>
            <h3 className="theme-heading text-lg font-semibold">
              {copy?.heritage_beginnings_heading ?? ''}
            </h3>
            <p className="text-sm text-muted-foreground">{copy?.heritage_beginnings_desc ?? ''}</p>
          </div>
          {beginningsLoading ? (
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="h-40 animate-pulse rounded-lg bg-muted" />
              <div className="h-40 animate-pulse rounded-lg bg-muted" />
            </div>
          ) : (
            <>
              <div className="grid gap-6 lg:grid-cols-[1fr_1fr]">
                {/* Left: Beginnings cards */}
                <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-1">
                  {beginnings?.map((option) => (
                    <Card
                      key={option.id}
                      className={cn(
                        'cursor-pointer transition-all',
                        draft.selected_beginnings?.id === option.id && 'ring-2 ring-primary',
                        draft.selected_beginnings?.id !== option.id &&
                          'hover:ring-1 hover:ring-primary/50',
                        detailBeginnings?.id === option.id &&
                          draft.selected_beginnings?.id !== option.id &&
                          'ring-1 ring-primary/30',
                        !option.is_accessible && 'cursor-not-allowed opacity-50'
                      )}
                      onClick={() => option.is_accessible && handleBeginningsSelect(option)}
                      onMouseEnter={() => option.is_accessible && setHoveredBeginnings(option)}
                      onMouseLeave={() => setHoveredBeginnings(null)}
                    >
                      {option.art_image && (
                        <div className="h-24 overflow-hidden rounded-t-lg">
                          <img
                            src={option.art_image}
                            alt={option.name}
                            className="h-full w-full object-cover"
                          />
                        </div>
                      )}
                      <CardHeader className="pb-2">
                        <CardTitle className="text-base">{option.name}</CardTitle>
                        {option.cg_point_cost > 0 && (
                          <span className="text-xs text-amber-600">
                            +{option.cg_point_cost} CG Points
                          </span>
                        )}
                      </CardHeader>
                      <CardContent>
                        <CardDescription className="line-clamp-3">
                          {option.description}
                        </CardDescription>
                      </CardContent>
                    </Card>
                  ))}
                  {(!beginnings || beginnings.length === 0) && (
                    <Card>
                      <CardContent className="py-8">
                        <p className="text-center text-sm text-muted-foreground">
                          No beginnings options available for this area.
                        </p>
                      </CardContent>
                    </Card>
                  )}
                </div>

                {/* Right: Detail panel (desktop only) */}
                {detailBeginnings && (
                  <div className="hidden lg:block">
                    <BeginningsDetailPanel
                      beginnings={detailBeginnings}
                      isSelected={draft.selected_beginnings?.id === detailBeginnings.id}
                    />
                  </div>
                )}
              </div>

              {/* Mobile: Detail panel below cards */}
              {detailBeginnings && (
                <div className="mt-2 lg:hidden">
                  <BeginningsDetailPanel
                    beginnings={detailBeginnings}
                    isSelected={draft.selected_beginnings?.id === detailBeginnings.id}
                  />
                </div>
              )}
            </>
          )}
        </section>

        {/* Species Selection - only show if beginnings selected */}
        {draft.selected_beginnings && (
          <section className="space-y-4">
            <div>
              <h3 className="theme-heading text-lg font-semibold">
                {copy?.heritage_species_heading ?? ''}
              </h3>
              <p className="text-sm text-muted-foreground">{copy?.heritage_species_desc ?? ''}</p>
            </div>
            {speciesLoading ? (
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="h-40 animate-pulse rounded-lg bg-muted" />
                <div className="h-40 animate-pulse rounded-lg bg-muted" />
              </div>
            ) : (
              <>
                <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                  {filteredSpecies?.map((species) => (
                    <SpeciesCard
                      key={species.id}
                      species={species}
                      isSelected={draft.selected_species?.id === species.id}
                      onSelect={() => handleSpeciesSelect(species.id)}
                      disabled={remainingPoints < 0 && draft.selected_species?.id !== species.id}
                      onHover={setHoveredSpecies}
                    />
                  ))}
                  {(!filteredSpecies || filteredSpecies.length === 0) && (
                    <Card>
                      <CardContent className="py-8">
                        <p className="text-center text-sm text-muted-foreground">
                          No species available for this beginnings path.
                        </p>
                      </CardContent>
                    </Card>
                  )}
                </div>

                {/* Mobile: Species detail below cards */}
                {draft.selected_species && (
                  <div className="mt-2 lg:hidden">
                    <SpeciesDetailPanel species={draft.selected_species} />
                  </div>
                )}
              </>
            )}
          </section>
        )}

        {/* Gender Selection */}
        <section className="space-y-4">
          <h3 className="theme-heading text-lg font-semibold">
            {copy?.heritage_gender_heading ?? ''}
          </h3>
          {gendersLoading ? (
            <div className="flex gap-2">
              <div className="h-10 w-20 animate-pulse rounded bg-muted" />
              <div className="h-10 w-20 animate-pulse rounded bg-muted" />
              <div className="h-10 w-32 animate-pulse rounded bg-muted" />
            </div>
          ) : (
            <div className="flex flex-wrap gap-2">
              {genders?.map((gender) => (
                <Button
                  key={gender.id}
                  variant={draft.selected_gender?.id === gender.id ? 'default' : 'outline'}
                  onClick={() => handleGenderChange(gender)}
                >
                  {gender.display_name}
                </Button>
              ))}
            </div>
          )}
          <p className="text-xs text-muted-foreground">
            Pronouns will be derived from your gender choice. You can customize them in-game.
          </p>
        </section>
      </motion.div>

      {/* Sidebar: CG Points Widget + Species Detail */}
      <div className="hidden lg:block">
        <div className="sticky top-4 space-y-4">
          <CGPointsWidget
            starting={startingPoints}
            spent={spentPoints}
            remaining={remainingPoints}
          />
          {draft.selected_beginnings && (
            <SpeciesDetailPanel species={hoveredSpecies ?? draft.selected_species ?? null} />
          )}
        </div>
      </div>
    </div>
  );
}

function SpeciesDetailPanel({ species }: { species: Species | null }) {
  if (!species) {
    return (
      <Card className="bg-muted/30">
        <CardContent className="py-8 text-center text-sm text-muted-foreground">
          Hover over a species to see its full description.
        </CardContent>
      </Card>
    );
  }

  return (
    <AnimatePresence mode="wait">
      <motion.div
        key={species.id}
        initial={{ opacity: 0, x: 10 }}
        animate={{ opacity: 1, x: 0 }}
        exit={{ opacity: 0, x: -10 }}
        transition={{ duration: 0.25 }}
      >
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">{species.name}</CardTitle>
            {species.parent_name && <CardDescription>{species.parent_name}</CardDescription>}
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="whitespace-pre-wrap leading-relaxed text-muted-foreground">
              {species.description}
            </p>
            <StatBonusBadges statBonuses={species.stat_bonuses} showHeader />
          </CardContent>
        </Card>
      </motion.div>
    </AnimatePresence>
  );
}

function BeginningsDetailPanel({
  beginnings,
  isSelected,
}: {
  beginnings: Beginnings;
  isSelected: boolean;
}) {
  const [color1, color2] = getGradientColors(beginnings.name);

  return (
    <AnimatePresence mode="wait">
      <motion.div
        key={beginnings.id}
        initial={{ opacity: 0, x: 10 }}
        animate={{ opacity: 1, x: 0 }}
        exit={{ opacity: 0, x: -10 }}
        transition={{ duration: 0.25 }}
        className="sticky top-4"
      >
        <Card className="overflow-hidden">
          {/* Header with art image or gradient fallback */}
          <div
            className="relative flex h-32 items-end p-6"
            style={{
              background: beginnings.art_image
                ? `url(${beginnings.art_image}) center/cover`
                : `linear-gradient(135deg, ${color1}, ${color2})`,
            }}
          >
            <div className="absolute inset-0 bg-gradient-to-t from-black/60 to-transparent" />
            <h3 className="theme-heading relative text-2xl font-bold text-white drop-shadow-lg">
              {beginnings.name}
            </h3>
            {isSelected && (
              <CheckCircle2 className="relative ml-auto h-6 w-6 text-white drop-shadow-lg" />
            )}
          </div>
          <CardContent className="p-6">
            <p className="whitespace-pre-wrap leading-relaxed text-muted-foreground">
              {beginnings.description}
            </p>
            {beginnings.cg_point_cost > 0 && (
              <p className="mt-4 text-sm text-amber-600">+{beginnings.cg_point_cost} CG Points</p>
            )}
            {!beginnings.is_accessible && (
              <p className="mt-4 text-sm text-destructive">
                This beginning is not currently accessible to your account.
              </p>
            )}
          </CardContent>
        </Card>
      </motion.div>
    </AnimatePresence>
  );
}

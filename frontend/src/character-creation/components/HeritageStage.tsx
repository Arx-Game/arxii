/**
 * Stage 2: Heritage Selection
 *
 * Handles:
 * - Beginnings selection (worldbuilding path)
 * - Species-area selection with costs and bonuses (gated by Beginnings)
 * - Gender selection (3 options)
 * - Age (18-65)
 *
 * Family selection has moved to LineageStage (Stage 3).
 * Pronouns are auto-derived at finalization.
 */

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';
import { motion } from 'framer-motion';
import {
  useBeginnings,
  useCGPointBudget,
  useGenders,
  useSpeciesOptions,
  useUpdateDraft,
} from '../queries';
import type { Beginnings, CharacterDraft, GenderOption } from '../types';
import { Stage } from '../types';
import { CGPointsWidget } from './CGPointsWidget';
import { SpeciesOptionCard } from './SpeciesOptionCard';

interface HeritageStageProps {
  draft: CharacterDraft;
  onStageSelect: (stage: Stage) => void;
}

// Age constraints for character creation
const AGE_MIN = 18;
const AGE_MAX = 65;

export function HeritageStage({ draft, onStageSelect }: HeritageStageProps) {
  const updateDraft = useUpdateDraft();

  // Fetch CG budget, beginnings, species options, and genders
  const { data: cgBudget } = useCGPointBudget();
  const { data: beginnings, isLoading: beginningsLoading } = useBeginnings(draft.selected_area?.id);
  const { data: speciesOptions, isLoading: speciesLoading } = useSpeciesOptions(
    draft.selected_area?.id
  );
  const { data: genders, isLoading: gendersLoading } = useGenders();

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
        // Clear species option when changing beginnings
        selected_species_option_id: null,
      },
    });
  };

  const handleSpeciesOptionSelect = (optionId: number) => {
    updateDraft.mutate({
      draftId: draft.id,
      data: {
        selected_species_option_id: optionId,
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

  const handleAgeChange = (value: string) => {
    const age = value ? parseInt(value, 10) : null;
    // Clamp to valid range if provided
    const clampedAge = age !== null ? Math.max(AGE_MIN, Math.min(AGE_MAX, age)) : null;
    updateDraft.mutate({
      draftId: draft.id,
      data: { age: clampedAge },
    });
  };

  // Filter species options based on selected beginnings
  const filteredSpeciesOptions = speciesOptions?.filter((option) => {
    if (!draft.selected_beginnings) return false;
    // If allows_all_species, show all options for this area
    if (draft.selected_beginnings.allows_all_species) return true;
    // Otherwise, only show options in the beginnings' species_option_ids
    return draft.selected_beginnings.species_option_ids.includes(option.id);
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
          <h2 className="text-2xl font-bold">Heritage</h2>
          <p className="mt-2 text-muted-foreground">
            Define your character's beginnings, species, and identity.
          </p>
        </div>

        {/* Beginnings Selection */}
        <section className="space-y-4">
          <div>
            <h3 className="text-lg font-semibold">Beginnings</h3>
            <p className="text-sm text-muted-foreground">
              Choose your character's origin story and worldbuilding context.
            </p>
          </div>
          {beginningsLoading ? (
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="h-40 animate-pulse rounded-lg bg-muted" />
              <div className="h-40 animate-pulse rounded-lg bg-muted" />
            </div>
          ) : (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {beginnings?.map((option) => (
                <Card
                  key={option.id}
                  className={cn(
                    'cursor-pointer transition-all',
                    draft.selected_beginnings?.id === option.id && 'ring-2 ring-primary',
                    draft.selected_beginnings?.id !== option.id &&
                      'hover:ring-1 hover:ring-primary/50',
                    !option.is_accessible && 'cursor-not-allowed opacity-50'
                  )}
                  onClick={() => option.is_accessible && handleBeginningsSelect(option)}
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
                    <CardDescription className="line-clamp-3">{option.description}</CardDescription>
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
          )}
        </section>

        {/* Species & Origin Selection - only show if beginnings selected */}
        {draft.selected_beginnings && (
          <section className="space-y-4">
            <div>
              <h3 className="text-lg font-semibold">Species & Origin</h3>
              <p className="text-sm text-muted-foreground">
                Choose your species and view associated costs and bonuses.
              </p>
            </div>
            {speciesLoading ? (
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="h-40 animate-pulse rounded-lg bg-muted" />
                <div className="h-40 animate-pulse rounded-lg bg-muted" />
              </div>
            ) : (
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {filteredSpeciesOptions?.map((option) => (
                  <SpeciesOptionCard
                    key={option.id}
                    option={option}
                    isSelected={draft.selected_species_option?.id === option.id}
                    onSelect={() => handleSpeciesOptionSelect(option.id)}
                    disabled={
                      remainingPoints < 0 && draft.selected_species_option?.id !== option.id
                    }
                  />
                ))}
                {(!filteredSpeciesOptions || filteredSpeciesOptions.length === 0) && (
                  <Card>
                    <CardContent className="py-8">
                      <p className="text-center text-sm text-muted-foreground">
                        No species options available for this beginnings path.
                      </p>
                    </CardContent>
                  </Card>
                )}
              </div>
            )}
          </section>
        )}

        {/* Gender Selection */}
        <section className="space-y-4">
          <h3 className="text-lg font-semibold">Gender</h3>
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

        {/* Age */}
        <section className="space-y-4">
          <h3 className="text-lg font-semibold">Age</h3>
          <div className="max-w-xs">
            <Input
              type="number"
              min={AGE_MIN}
              max={AGE_MAX}
              value={draft.age ?? ''}
              onChange={(e) => handleAgeChange(e.target.value)}
              onBlur={(e) => handleAgeChange(e.target.value)}
              placeholder={`Enter age (${AGE_MIN}-${AGE_MAX})`}
            />
            <p className="mt-1 text-xs text-muted-foreground">
              Age must be between {AGE_MIN} and {AGE_MAX} years.
            </p>
          </div>
        </section>
      </motion.div>

      {/* Sidebar: CG Points Widget */}
      <div className="hidden lg:block">
        <CGPointsWidget starting={startingPoints} spent={spentPoints} remaining={remainingPoints} />
      </div>
    </div>
  );
}

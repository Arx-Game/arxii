/**
 * Stage 2: Combined Heritage & Lineage Selection
 *
 * Unified stage handling:
 * - CG Points budget tracking
 * - Species-area selection with costs and bonuses
 * - Heritage type (normal/special)
 * - Gender, pronouns, and age
 * - Family selection (join/create/orphan)
 */

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { cn } from '@/lib/utils';
import { motion } from 'framer-motion';
import { Sparkles, User } from 'lucide-react';
import { useCGPointBudget, useSpeciesOptions, useUpdateDraft } from '../queries';
import type { CharacterDraft, Gender, SpecialHeritage } from '../types';
import { DEFAULT_PRONOUNS, Stage } from '../types';
import { CGPointsWidget } from './CGPointsWidget';
import { FamilySelection } from './FamilySelection';
import { SpeciesOptionCard } from './SpeciesOptionCard';

interface HeritageStageProps {
  draft: CharacterDraft;
  onStageSelect: (stage: Stage) => void;
}

const GENDER_OPTIONS: { value: Gender; label: string }[] = [
  { value: 'male', label: 'Male' },
  { value: 'female', label: 'Female' },
  { value: 'nonbinary', label: 'Non-binary' },
  { value: 'other', label: 'Other' },
];

export function HeritageStage({ draft, onStageSelect }: HeritageStageProps) {
  const updateDraft = useUpdateDraft();
  const specialHeritages = draft.selected_area?.special_heritages ?? [];
  const hasSpecialHeritages = specialHeritages.length > 0;

  // Fetch CG budget and species options
  const { data: cgBudget } = useCGPointBudget();
  const { data: speciesOptions, isLoading: speciesLoading } = useSpeciesOptions(
    draft.selected_area?.id
  );

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

  const handleHeritageSelect = (heritage: SpecialHeritage | null) => {
    updateDraft.mutate({
      draftId: draft.id,
      data: {
        selected_heritage_id: heritage?.id ?? null,
        // Clear species option when changing heritage
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

  const handleGenderChange = (gender: Gender) => {
    const pronouns = DEFAULT_PRONOUNS[gender];
    updateDraft.mutate({
      draftId: draft.id,
      data: {
        gender,
        pronoun_subject: pronouns.subject,
        pronoun_object: pronouns.object,
        pronoun_possessive: pronouns.possessive,
      },
    });
  };

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
          <h2 className="text-2xl font-bold">Heritage & Lineage</h2>
          <p className="mt-2 text-muted-foreground">
            Define your character's origins, species, identity, and family background.
          </p>
        </div>

        {/* Heritage Type Selection */}
        {hasSpecialHeritages && (
          <section className="space-y-4">
            <h3 className="text-lg font-semibold">Heritage Type</h3>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {/* Normal Upbringing */}
              <Card
                className={cn(
                  'cursor-pointer transition-all',
                  !draft.selected_heritage && 'ring-2 ring-primary',
                  draft.selected_heritage && 'hover:ring-1 hover:ring-primary/50'
                )}
                onClick={() => handleHeritageSelect(null)}
              >
                <CardHeader className="pb-2">
                  <div className="flex items-center gap-2">
                    <User className="h-5 w-5" />
                    <CardTitle className="text-base">Normal Upbringing</CardTitle>
                  </div>
                </CardHeader>
                <CardContent>
                  <CardDescription>
                    Raised in {draft.selected_area.name} with a conventional background.
                  </CardDescription>
                </CardContent>
              </Card>

              {/* Special Heritages */}
              {specialHeritages.map((heritage) => (
                <Card
                  key={heritage.id}
                  className={cn(
                    'cursor-pointer transition-all',
                    draft.selected_heritage?.id === heritage.id && 'ring-2 ring-primary',
                    draft.selected_heritage?.id !== heritage.id &&
                      'hover:ring-1 hover:ring-primary/50'
                  )}
                  onClick={() => handleHeritageSelect(heritage)}
                >
                  <CardHeader className="pb-2">
                    <div className="flex items-center gap-2">
                      <Sparkles className="h-5 w-5 text-amber-500" />
                      <CardTitle className="text-base">{heritage.name}</CardTitle>
                    </div>
                  </CardHeader>
                  <CardContent>
                    <CardDescription>{heritage.description}</CardDescription>
                  </CardContent>
                </Card>
              ))}
            </div>
          </section>
        )}

        {/* Species & Origin Selection */}
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
              {speciesOptions?.map((option) => (
                <SpeciesOptionCard
                  key={option.id}
                  option={option}
                  isSelected={draft.selected_species_option?.id === option.id}
                  onSelect={() => handleSpeciesOptionSelect(option.id)}
                  disabled={remainingPoints < 0 && draft.selected_species_option?.id !== option.id}
                />
              ))}
              {(!speciesOptions || speciesOptions.length === 0) && (
                <Card>
                  <CardContent className="py-8">
                    <p className="text-center text-sm text-muted-foreground">
                      No species options available for this area.
                    </p>
                  </CardContent>
                </Card>
              )}
            </div>
          )}
        </section>

        {/* Gender Selection */}
        <section className="space-y-4">
          <h3 className="text-lg font-semibold">Gender</h3>
          <div className="flex flex-wrap gap-2">
            {GENDER_OPTIONS.map((option) => (
              <Button
                key={option.value}
                variant={draft.gender === option.value ? 'default' : 'outline'}
                onClick={() => handleGenderChange(option.value)}
              >
                {option.label}
              </Button>
            ))}
          </div>
        </section>

        {/* Pronouns */}
        <section className="space-y-4">
          <h3 className="text-lg font-semibold">Pronouns</h3>
          <p className="text-sm text-muted-foreground">
            Customize how your character is referred to in-game.
          </p>
          <div className="grid max-w-lg gap-4 sm:grid-cols-3">
            <div className="space-y-2">
              <Label htmlFor="pronoun-subject">Subject</Label>
              <Input
                id="pronoun-subject"
                value={draft.pronoun_subject}
                onChange={(e) =>
                  updateDraft.mutate({
                    draftId: draft.id,
                    data: { pronoun_subject: e.target.value },
                  })
                }
                placeholder="they"
              />
              <p className="text-xs text-muted-foreground">e.g., "They walked"</p>
            </div>
            <div className="space-y-2">
              <Label htmlFor="pronoun-object">Object</Label>
              <Input
                id="pronoun-object"
                value={draft.pronoun_object}
                onChange={(e) =>
                  updateDraft.mutate({
                    draftId: draft.id,
                    data: { pronoun_object: e.target.value },
                  })
                }
                placeholder="them"
              />
              <p className="text-xs text-muted-foreground">e.g., "I saw them"</p>
            </div>
            <div className="space-y-2">
              <Label htmlFor="pronoun-possessive">Possessive</Label>
              <Input
                id="pronoun-possessive"
                value={draft.pronoun_possessive}
                onChange={(e) =>
                  updateDraft.mutate({
                    draftId: draft.id,
                    data: { pronoun_possessive: e.target.value },
                  })
                }
                placeholder="theirs"
              />
              <p className="text-xs text-muted-foreground">e.g., "It's theirs"</p>
            </div>
          </div>
        </section>

        {/* Age */}
        <section className="space-y-4">
          <h3 className="text-lg font-semibold">Age</h3>
          <div className="max-w-xs">
            <Input
              type="number"
              min={1}
              max={9999}
              value={draft.age ?? ''}
              onChange={(e) =>
                updateDraft.mutate({
                  draftId: draft.id,
                  data: {
                    age: e.target.value ? parseInt(e.target.value, 10) : null,
                  },
                })
              }
              placeholder="Enter age in years"
            />
            <p className="mt-1 text-xs text-muted-foreground">Age in years (varies by species)</p>
          </div>
        </section>

        {/* Family & Lineage */}
        {/* Only show if NOT a special heritage, since special heritages have "Unknown" family */}
        {!draft.selected_heritage && (
          <section className="space-y-4">
            <div>
              <h3 className="text-lg font-semibold">Family & Lineage</h3>
              <p className="text-sm text-muted-foreground">
                Choose your character's family background.
              </p>
            </div>
            <FamilySelection draft={draft} areaId={draft.selected_area.id} />
          </section>
        )}

        {/* Special Heritage Family Display */}
        {draft.selected_heritage && (
          <section className="space-y-4">
            <h3 className="text-lg font-semibold">Family & Lineage</h3>
            <Card className="max-w-md">
              <CardHeader>
                <CardTitle className="text-base">
                  {draft.selected_heritage.family_display}
                </CardTitle>
              </CardHeader>
              <CardContent>
                <CardDescription>
                  As a {draft.selected_heritage.name}, your true family origins are shrouded in
                  mystery. This may be discovered through gameplay.
                </CardDescription>
              </CardContent>
            </Card>
          </section>
        )}
      </motion.div>

      {/* Sidebar: CG Points Widget */}
      <div className="hidden lg:block">
        <CGPointsWidget starting={startingPoints} spent={spentPoints} remaining={remainingPoints} />
      </div>
    </div>
  );
}

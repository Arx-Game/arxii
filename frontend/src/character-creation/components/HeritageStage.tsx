/**
 * Stage 2: Heritage Selection
 *
 * Handles heritage type (normal/special), species, gender, pronouns, and age.
 */

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { cn } from '@/lib/utils';
import { motion } from 'framer-motion';
import { Sparkles, User } from 'lucide-react';
import { useSpecies, useUpdateDraft } from '../queries';
import type { CharacterDraft, Gender, SpecialHeritage } from '../types';
import { DEFAULT_PRONOUNS, Stage } from '../types';

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

  // Fetch species based on area and heritage selection
  const { data: species, isLoading: speciesLoading } = useSpecies(
    draft.selected_area?.id,
    draft.selected_heritage?.id
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
        // Clear species when changing heritage since available species may change
        species: '',
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

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -20 }}
      transition={{ duration: 0.3 }}
      className="space-y-8"
    >
      <div>
        <h2 className="text-2xl font-bold">Define Your Heritage</h2>
        <p className="mt-2 text-muted-foreground">
          Choose your character's origins, species, and basic identity.
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

      {/* Species Selection */}
      <section className="space-y-4">
        <h3 className="text-lg font-semibold">Species</h3>
        {speciesLoading ? (
          <div className="h-10 animate-pulse rounded bg-muted" />
        ) : (
          <Select
            value={draft.species}
            onValueChange={(value) =>
              updateDraft.mutate({ draftId: draft.id, data: { species: value } })
            }
          >
            <SelectTrigger className="w-full max-w-xs">
              <SelectValue placeholder="Select species" />
            </SelectTrigger>
            <SelectContent>
              {species?.map((s) => (
                <SelectItem key={s.id} value={s.name}>
                  {s.name}
                </SelectItem>
              ))}
              {(!species || species.length === 0) && (
                <SelectItem value="" disabled>
                  No species available
                </SelectItem>
              )}
            </SelectContent>
          </Select>
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
    </motion.div>
  );
}

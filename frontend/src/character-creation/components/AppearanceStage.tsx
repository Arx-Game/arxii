/**
 * Stage 7: Appearance
 *
 * Physical characteristics: age, height, build, form traits (hair, eyes, etc.), description.
 */

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Slider } from '@/components/ui/slider';
import { Textarea } from '@/components/ui/textarea';
import { cn } from '@/lib/utils';
import { motion } from 'framer-motion';
import { useCallback, useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import {
  useBuilds,
  useCGExplanations,
  useFormOptions,
  useHeightBands,
  useUpdateDraft,
} from '../queries';
import type { Build, CharacterDraft, FormTraitWithOptions, HeightBand } from '../types';

interface AppearanceStageProps {
  draft: CharacterDraft;
  isStaff?: boolean;
  onRegisterBeforeLeave?: (check: () => Promise<boolean>) => (() => void) | void;
}

interface AppearanceFormValues {
  description: string;
}

const AGE_MIN = 18;
const AGE_MAX = 65;
const AGE_DEFAULT = 22;

export function AppearanceStage({
  draft,
  isStaff = false,
  onRegisterBeforeLeave,
}: AppearanceStageProps) {
  const updateDraft = useUpdateDraft();
  const { data: copy } = useCGExplanations();
  const { data: heightBands, isLoading: heightBandsLoading } = useHeightBands();
  const { data: builds, isLoading: buildsLoading } = useBuilds();
  const { data: formOptions, isLoading: formOptionsLoading } = useFormOptions(
    draft.selected_species?.id
  );
  const draftData = draft.draft_data;

  const { register, getValues, reset, formState } = useForm<AppearanceFormValues>({
    defaultValues: {
      description: draftData.description ?? '',
    },
  });

  const saveDescription = useCallback(async () => {
    if (!formState.isDirty) return true;
    try {
      await updateDraft.mutateAsync({
        draftId: draft.id,
        data: {
          draft_data: {
            description: getValues('description'),
          },
        },
      });
      return true;
    } catch {
      return window.confirm('Failed to save description. Discard changes and continue?');
    }
  }, [draft.id, updateDraft, formState.isDirty, getValues, reset]);

  useEffect(() => {
    if (!onRegisterBeforeLeave) return;
    // Return the unregister as cleanup (2026-07 audit): without it, an
    // unmounted stage's save closure stayed registered and re-fired on every
    // later navigation, PATCHing stale values over newer edits.
    return onRegisterBeforeLeave(saveDescription) ?? undefined;
  }, [onRegisterBeforeLeave, saveDescription]);

  const [localAge, setLocalAge] = useState(String(draft.age ?? AGE_DEFAULT));

  // Auto-save default age on first visit when unset, so backend sees age != None
  useEffect(() => {
    if (draft.age === null || draft.age === undefined) {
      updateDraft.mutate({ draftId: draft.id, data: { age: AGE_DEFAULT } });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft.id]);

  const commitAge = () => {
    const parsed = parseInt(localAge, 10);
    const clamped = Number.isNaN(parsed)
      ? AGE_DEFAULT
      : Math.max(AGE_MIN, Math.min(AGE_MAX, parsed));
    setLocalAge(String(clamped));
    if (clamped !== draft.age) {
      updateDraft.mutate({
        draftId: draft.id,
        data: { age: clamped },
      });
    }
  };

  const handleHeightBandSelect = (band: HeightBand) => {
    const midpoint = Math.floor((band.min_inches + band.max_inches) / 2);
    updateDraft.mutate({
      draftId: draft.id,
      data: {
        height_band_id: band.id,
        height_inches: midpoint,
      },
    });
  };

  // Local thumb position while dragging; null = track the draft value.
  const [heightDraft, setHeightDraft] = useState<number | null>(null);

  const handleHeightInchesCommit = (value: number[]) => {
    setHeightDraft(null);
    updateDraft.mutate({
      draftId: draft.id,
      data: { height_inches: value[0] },
    });
  };

  const handleBuildSelect = (build: Build) => {
    updateDraft.mutate({
      draftId: draft.id,
      data: { build_id: build.id },
    });
  };

  const handleFormTraitChange = (traitName: string, optionId: number) => {
    updateDraft.mutate({
      draftId: draft.id,
      data: {
        draft_data: {
          ...draftData,
          form_traits: {
            ...(draftData.form_traits ?? {}),
            [traitName]: optionId,
          },
        },
      },
    });
  };

  // #2632 — optional per-trait flavor text ("red" + "flowing crimson"). The
  // normalized option stays the succinct/mechanical value; this text is what
  // other characters read. Commit-on-blur to avoid a per-keystroke PATCH storm.
  const getTraitDescriptor = (traitName: string): string => {
    const descriptors = draftData.form_trait_descriptors as Record<string, string> | undefined;
    return descriptors?.[traitName] ?? '';
  };

  const handleTraitDescriptorCommit = (traitName: string, text: string) => {
    if (text.trim() === getTraitDescriptor(traitName).trim()) return;
    updateDraft.mutate({
      draftId: draft.id,
      data: {
        draft_data: {
          ...draftData,
          form_trait_descriptors: {
            ...((draftData.form_trait_descriptors as Record<string, string>) ?? {}),
            [traitName]: text.trim(),
          },
        },
      },
    });
  };

  const formatHeight = (inches: number): string => {
    const feet = Math.floor(inches / 12);
    const remainingInches = inches % 12;
    return `${feet}'${remainingInches}"`;
  };

  // Get the selected option for a form trait
  const getSelectedOptionId = (traitName: string): string => {
    const formTraits = draftData.form_traits as Record<string, number> | undefined;
    const selectedId = formTraits?.[traitName];
    return selectedId ? String(selectedId) : '';
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
        <h2 className="theme-heading text-2xl font-bold">{copy?.appearance_heading ?? ''}</h2>
        <p className="mt-2 text-muted-foreground">{copy?.appearance_intro ?? ''}</p>
      </div>

      {/* Age */}
      <section className="space-y-4">
        <h3 className="theme-heading text-lg font-semibold">Age</h3>
        <div className="max-w-xs">
          <Input
            type="number"
            min={AGE_MIN}
            max={AGE_MAX}
            value={localAge}
            onChange={(e) => setLocalAge(e.target.value)}
            onBlur={commitAge}
            placeholder={`Enter age (${AGE_MIN}-${AGE_MAX})`}
          />
          <p className="mt-1 text-xs text-muted-foreground">
            Age must be between {AGE_MIN} and {AGE_MAX} years.
          </p>
        </div>
      </section>

      {/* Height Band Selection */}
      <section className="space-y-4">
        <h3 className="theme-heading text-lg font-semibold">Height</h3>
        <p className="text-sm text-muted-foreground">
          Select your height category, then fine-tune your exact height.
        </p>
        {heightBandsLoading ? (
          <div className="flex gap-2">
            {[1, 2, 3, 4, 5].map((i) => (
              <div key={i} className="h-10 w-24 animate-pulse rounded bg-muted" />
            ))}
          </div>
        ) : (
          <div className="flex flex-wrap gap-2">
            {heightBands?.map((band) => (
              <Button
                key={band.id}
                variant={draft.height_band?.id === band.id ? 'default' : 'outline'}
                onClick={() => handleHeightBandSelect(band)}
                className={cn(
                  !band.is_cg_selectable &&
                    isStaff &&
                    'border-red-500 text-red-500 hover:bg-red-500/10 hover:text-red-500'
                )}
              >
                {band.display_name}
              </Button>
            ))}
          </div>
        )}

        {draft.height_band && (
          <div className="max-w-md space-y-2">
            <div className="flex justify-between text-sm">
              <span>{formatHeight(draft.height_band.min_inches)}</span>
              <span className="font-semibold">
                {(heightDraft ?? draft.height_inches)
                  ? formatHeight(heightDraft ?? draft.height_inches!)
                  : '—'}
              </span>
              <span>{formatHeight(draft.height_band.max_inches)}</span>
            </div>
            <Slider
              value={[heightDraft ?? draft.height_inches ?? draft.height_band.min_inches]}
              min={draft.height_band.min_inches}
              max={draft.height_band.max_inches}
              step={1}
              // Commit-only PATCH (2026-07 audit): onValueChange fired one
              // request per drag tick — a request storm whose out-of-order
              // responses rubber-banded the thumb. Local state keeps the
              // thumb tracking during the drag.
              onValueChange={(value) => setHeightDraft(value[0])}
              onValueCommit={handleHeightInchesCommit}
            />
            <p className="text-xs text-muted-foreground">
              Other characters will see you as "{draft.height_band.display_name}" rather than your
              exact height.
            </p>
          </div>
        )}
      </section>

      {/* Build Selection */}
      <section className="space-y-4">
        <h3 className="theme-heading text-lg font-semibold">Build</h3>
        <p className="text-sm text-muted-foreground">Select your body type.</p>
        {buildsLoading ? (
          <div className="flex gap-2">
            {[1, 2, 3, 4, 5, 6].map((i) => (
              <div key={i} className="h-10 w-24 animate-pulse rounded bg-muted" />
            ))}
          </div>
        ) : (
          <div className="flex flex-wrap gap-2">
            {builds?.map((build) => (
              <Button
                key={build.id}
                variant={draft.build?.id === build.id ? 'default' : 'outline'}
                onClick={() => handleBuildSelect(build)}
                className={cn(
                  !build.is_cg_selectable &&
                    isStaff &&
                    'border-red-500 text-red-500 hover:bg-red-500/10 hover:text-red-500'
                )}
              >
                {build.display_name}
              </Button>
            ))}
          </div>
        )}
      </section>

      {/* Form Traits (Hair, Eyes, Skin, etc.) */}
      {draft.selected_species && (
        <section className="space-y-4">
          <h3 className="theme-heading text-lg font-semibold">Physical Features</h3>
          <p className="text-sm text-muted-foreground">
            Select your character's physical features.
          </p>
          {formOptionsLoading ? (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {[1, 2, 3, 4].map((i) => (
                <div key={i} className="h-16 animate-pulse rounded bg-muted" />
              ))}
            </div>
          ) : formOptions && formOptions.length > 0 ? (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {formOptions.map((formOption: FormTraitWithOptions) => (
                <div key={formOption.trait.id} className="space-y-2">
                  <Label htmlFor={`trait-${formOption.trait.name}`}>
                    {formOption.trait.display_name}
                  </Label>
                  <Select
                    value={getSelectedOptionId(formOption.trait.name)}
                    onValueChange={(value) =>
                      handleFormTraitChange(formOption.trait.name, parseInt(value, 10))
                    }
                  >
                    <SelectTrigger id={`trait-${formOption.trait.name}`}>
                      <SelectValue placeholder={`Select ${formOption.trait.display_name}`} />
                    </SelectTrigger>
                    <SelectContent className="max-h-60 overflow-y-auto">
                      {formOption.options.map((option) => (
                        <SelectItem key={option.id} value={String(option.id)}>
                          {option.display_name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <Input
                    aria-label={`Describe your ${formOption.trait.display_name.toLowerCase()}`}
                    placeholder="Describe it (optional) — e.g. flowing crimson"
                    defaultValue={getTraitDescriptor(formOption.trait.name)}
                    onBlur={(e) =>
                      handleTraitDescriptorCommit(formOption.trait.name, e.target.value)
                    }
                  />
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm italic text-muted-foreground">
              No physical features available for this species.
            </p>
          )}
        </section>
      )}

      {/* Description */}
      <section className="space-y-4">
        <h3 className="theme-heading text-lg font-semibold">Physical Description</h3>
        <div className="space-y-2">
          <Label htmlFor="description">Description</Label>
          <Textarea
            id="description"
            {...register('description')}
            placeholder="Describe your character's physical appearance..."
            rows={4}
            className="resize-y"
          />
          <p className="text-xs text-muted-foreground">
            (Optional, appended to automatic descriptions)
          </p>
        </div>
      </section>
    </motion.div>
  );
}

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
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Slider } from '@/components/ui/slider';
import { Textarea } from '@/components/ui/textarea';
import { cn } from '@/lib/utils';
import { motion } from 'framer-motion';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useForm } from 'react-hook-form';
import {
  useBuilds,
  useCGExplanations,
  useFormOptions,
  useHeightBands,
  useUpdateDraft,
} from '../queries';
import { MarkingsEditor } from './MarkingsEditor';
import type {
  Build,
  CharacterDraft,
  FormTraitOption,
  FormTrait,
  HeightBand,
  InheritedTraitGroup,
} from '../types';

/** A trait row for rendering: own palette + inherited groups (#2815). */
interface MergedTraitOptions {
  trait: FormTrait;
  is_required: boolean;
  options: FormTraitOption[];
  inherited: InheritedTraitGroup[];
}

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
// Eternal-youth species (elves, vampires) lock their apparent age in the
// early 20s (#2756) — mirrors the server-side cap.
const AGE_MAX_ETERNAL_YOUTH = 29;
const AGE_DEFAULT = 22;

const MONTH_NAMES = [
  'January',
  'February',
  'March',
  'April',
  'May',
  'June',
  'July',
  'August',
  'September',
  'October',
  'November',
  'December',
];
// 29 for February: leap-day birthdays are legal (#2756).
const DAYS_IN_MONTH = [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];

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
    draft.selected_species?.id,
    draft.id
  );
  const draftData = draft.draft_data;

  // Merge own-palette traits with inherited cross-line groups (#2815). An
  // inherited group for a trait outside the own palette (e.g. a pinned value
  // on a trait the species doesn't normally offer) gets its own row.
  const mergedFormOptions = useMemo<MergedTraitOptions[]>(() => {
    if (!formOptions) return [];
    const rows: MergedTraitOptions[] = formOptions.traits.map((entry) => ({
      trait: entry.trait,
      is_required: entry.is_required,
      options: entry.options,
      inherited: [],
    }));
    const byTraitId = new Map(rows.map((row) => [row.trait.id, row]));
    for (const group of formOptions.inherited) {
      const row = byTraitId.get(group.trait.id);
      if (row) {
        row.inherited.push(group);
      } else {
        const newRow: MergedTraitOptions = {
          trait: group.trait,
          is_required: false,
          options: [],
          inherited: [group],
        };
        byTraitId.set(group.trait.id, newRow);
        rows.push(newRow);
      }
    }
    return rows;
  }, [formOptions]);

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
  // Eternal-youth species cap their age input (#2756); server enforces too.
  const ageMax = draft.selected_species?.eternal_youth ? AGE_MAX_ETERNAL_YOUTH : AGE_MAX;

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
      : Math.max(AGE_MIN, Math.min(ageMax, parsed));
    setLocalAge(String(clamped));
    if (clamped !== draft.age) {
      updateDraft.mutate({
        draftId: draft.id,
        data: { age: clamped },
      });
    }
  };

  // Celebrated birthday (#2756) — waking day for Sleeper beginnings.
  const birthdayMonth = draft.birthday_month;
  const birthdayDay = draft.birthday_day;
  const maxDay = birthdayMonth ? DAYS_IN_MONTH[birthdayMonth - 1] : 31;

  const commitBirthday = (month: number | null, day: number | null) => {
    const clampedDay =
      month !== null && day !== null ? Math.max(1, Math.min(DAYS_IN_MONTH[month - 1], day)) : day;
    updateDraft.mutate({
      draftId: draft.id,
      data: { birthday_month: month, birthday_day: clampedDay },
    });
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
            max={ageMax}
            value={localAge}
            onChange={(e) => setLocalAge(e.target.value)}
            onBlur={commitAge}
            placeholder={`Enter age (${AGE_MIN}-${ageMax})`}
          />
          <p className="mt-1 text-xs text-muted-foreground">
            Age must be between {AGE_MIN} and {ageMax} years.
            {draft.selected_species?.eternal_youth &&
              ' Your species keeps its eternal youth; apparent age locks in the early twenties.'}
          </p>
        </div>
      </section>

      {/* Birthday */}
      <section className="space-y-4">
        <h3 className="theme-heading text-lg font-semibold">Birthday</h3>
        <p className="text-sm text-muted-foreground">
          The day your character celebrates each year. Friends will see it coming up in the Town
          Crier&apos;s tidings.
        </p>
        <div className="flex max-w-md gap-3">
          <div className="flex-1">
            <Label className="text-xs">Month</Label>
            <Select
              value={birthdayMonth ? String(birthdayMonth) : ''}
              onValueChange={(value) => commitBirthday(parseInt(value, 10), birthdayDay ?? 1)}
            >
              <SelectTrigger>
                <SelectValue placeholder="Month" />
              </SelectTrigger>
              <SelectContent>
                {MONTH_NAMES.map((name, index) => (
                  <SelectItem key={name} value={String(index + 1)}>
                    {name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="w-28">
            <Label className="text-xs">Day</Label>
            <Input
              type="number"
              min={1}
              max={maxDay}
              value={birthdayDay ?? ''}
              onChange={(e) => {
                const parsed = parseInt(e.target.value, 10);
                if (!Number.isNaN(parsed) && birthdayMonth) {
                  commitBirthday(birthdayMonth, parsed);
                }
              }}
              placeholder="Day"
              disabled={!birthdayMonth}
            />
          </div>
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
                  : '-'}
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
          ) : mergedFormOptions.length > 0 ? (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {mergedFormOptions.map((formOption) => (
                <div key={formOption.trait.id} className="space-y-2">
                  <Label htmlFor={`trait-${formOption.trait.name}`}>
                    {formOption.trait.display_name}
                    {formOption.is_required && (
                      <span
                        className="ml-1 text-destructive"
                        title="Required for your species"
                        aria-label="required"
                      >
                        *
                      </span>
                    )}
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
                      {formOption.inherited.map((group) => (
                        <SelectGroup key={`${formOption.trait.id}-${group.source}`}>
                          <SelectLabel className="text-accent-foreground">
                            From your {group.source}
                          </SelectLabel>
                          {group.options.map((option) => (
                            <SelectItem key={option.id} value={String(option.id)}>
                              {option.display_name}
                            </SelectItem>
                          ))}
                        </SelectGroup>
                      ))}
                    </SelectContent>
                  </Select>
                  <Input
                    aria-label={`Describe your ${formOption.trait.display_name.toLowerCase()}`}
                    placeholder="Describe it (optional): e.g. flowing crimson"
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

      {/* Body markings (#2985) */}
      <section className="space-y-4">
        <MarkingsEditor />
      </section>
    </motion.div>
  );
}

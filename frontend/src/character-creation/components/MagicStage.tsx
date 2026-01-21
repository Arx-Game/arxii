/**
 * Stage 7: Magic
 *
 * Handles:
 * - Aura distribution (Celestial/Primal/Abyssal percentages summing to 100)
 * - Gift selection
 * - Personal resonance selection
 * - Anima ritual design
 * - Optional Glimpse story
 */

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Slider } from '@/components/ui/slider';
import { Textarea } from '@/components/ui/textarea';
import { cn } from '@/lib/utils';
import { motion } from 'framer-motion';
import { CheckCircle2, Sparkles, Sun, TreePine, Moon } from 'lucide-react';
import {
  useAffinities,
  useAnimaRitualTypes,
  useGifts,
  useResonances,
  useUpdateDraft,
} from '../queries';
import type { AnimaRitualType, CharacterDraft, GiftListItem, Resonance } from '../types';

interface MagicStageProps {
  draft: CharacterDraft;
}

const AURA_TOTAL = 100;
const DEFAULT_AURA = 34; // Close to 33.33

export function MagicStage({ draft }: MagicStageProps) {
  const updateDraft = useUpdateDraft();
  const { data: affinities, isLoading: affinitiesLoading } = useAffinities();
  const { data: gifts, isLoading: giftsLoading } = useGifts();
  const { data: resonances, isLoading: resonancesLoading } = useResonances();
  const { data: ritualTypes, isLoading: ritualTypesLoading } = useAnimaRitualTypes();

  const draftData = draft.draft_data;

  // Get current aura values with defaults
  const auraCelestial = draftData.aura_celestial ?? DEFAULT_AURA;
  const auraPrimal = draftData.aura_primal ?? DEFAULT_AURA;
  const auraAbyssal = draftData.aura_abyssal ?? AURA_TOTAL - DEFAULT_AURA * 2;

  // Get affinity colors and icons
  const getAffinityStyle = (type: string) => {
    switch (type) {
      case 'celestial':
        return {
          icon: Sun,
          bgClass: 'bg-amber-500/10',
          borderClass: 'border-amber-500/50',
          textClass: 'text-amber-500',
          sliderClass: '[&_[role=slider]]:bg-amber-500',
        };
      case 'primal':
        return {
          icon: TreePine,
          bgClass: 'bg-emerald-500/10',
          borderClass: 'border-emerald-500/50',
          textClass: 'text-emerald-500',
          sliderClass: '[&_[role=slider]]:bg-emerald-500',
        };
      case 'abyssal':
        return {
          icon: Moon,
          bgClass: 'bg-violet-500/10',
          borderClass: 'border-violet-500/50',
          textClass: 'text-violet-500',
          sliderClass: '[&_[role=slider]]:bg-violet-500',
        };
      default:
        return {
          icon: Sparkles,
          bgClass: 'bg-muted',
          borderClass: 'border-muted',
          textClass: 'text-muted-foreground',
          sliderClass: '',
        };
    }
  };

  // Handle aura slider changes - redistribute among others proportionally
  const handleAuraChange = (affinity: 'celestial' | 'primal' | 'abyssal', newValue: number) => {
    const current = { celestial: auraCelestial, primal: auraPrimal, abyssal: auraAbyssal };
    const oldValue = current[affinity];
    const diff = newValue - oldValue;

    // Get the other two affinities
    const others = (['celestial', 'primal', 'abyssal'] as const).filter((a) => a !== affinity);
    const otherSum = others.reduce((sum, a) => sum + current[a], 0);

    const newValues = { ...current, [affinity]: newValue };

    if (otherSum > 0 && diff !== 0) {
      // Redistribute the difference proportionally
      others.forEach((other) => {
        const proportion = current[other] / otherSum;
        const adjustment = Math.round(diff * proportion);
        newValues[other] = Math.max(0, current[other] - adjustment);
      });

      // Ensure total is exactly 100
      const total = Object.values(newValues).reduce((sum, v) => sum + v, 0);
      if (total !== AURA_TOTAL) {
        // Adjust the largest of the other two to compensate
        const largerOther = newValues[others[0]] >= newValues[others[1]] ? others[0] : others[1];
        newValues[largerOther] += AURA_TOTAL - total;
        newValues[largerOther] = Math.max(0, newValues[largerOther]);
      }
    } else if (diff !== 0) {
      // If others are at 0, just clamp the new value
      newValues[affinity] = Math.min(AURA_TOTAL, Math.max(0, newValue));
    }

    updateDraft.mutate({
      draftId: draft.id,
      data: {
        draft_data: {
          ...draftData,
          aura_celestial: newValues.celestial,
          aura_primal: newValues.primal,
          aura_abyssal: newValues.abyssal,
        },
      },
    });
  };

  const handleGiftSelect = (gift: GiftListItem) => {
    updateDraft.mutate({
      draftId: draft.id,
      data: {
        draft_data: {
          ...draftData,
          selected_gift_id: gift.id,
        },
      },
    });
  };

  const handleResonanceToggle = (resonance: Resonance) => {
    const currentIds = draftData.selected_resonance_ids ?? [];
    const maxResonances = 3;

    let newIds: number[];
    if (currentIds.includes(resonance.id)) {
      // Remove if already selected
      newIds = currentIds.filter((id) => id !== resonance.id);
    } else if (currentIds.length < maxResonances) {
      // Add if under limit
      newIds = [...currentIds, resonance.id];
    } else {
      // At limit - don't add
      return;
    }

    updateDraft.mutate({
      draftId: draft.id,
      data: {
        draft_data: {
          ...draftData,
          selected_resonance_ids: newIds,
        },
      },
    });
  };

  const handleRitualTypeSelect = (ritualType: AnimaRitualType) => {
    updateDraft.mutate({
      draftId: draft.id,
      data: {
        draft_data: {
          ...draftData,
          selected_ritual_type_id: ritualType.id,
        },
      },
    });
  };

  const handleRitualDescriptionChange = (value: string) => {
    updateDraft.mutate({
      draftId: draft.id,
      data: {
        draft_data: {
          ...draftData,
          anima_ritual_description: value,
        },
      },
    });
  };

  const handleGlimpseStoryChange = (value: string) => {
    updateDraft.mutate({
      draftId: draft.id,
      data: {
        draft_data: {
          ...draftData,
          glimpse_story: value,
        },
      },
    });
  };

  const selectedResonanceIds = draftData.selected_resonance_ids ?? [];
  const maxResonances = 3;

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -20 }}
      transition={{ duration: 0.3 }}
      className="space-y-8"
    >
      <div>
        <h2 className="text-2xl font-bold">Magic</h2>
        <p className="mt-2 text-muted-foreground">
          Define your character's magical nature and abilities.
        </p>
      </div>

      {/* Aura Distribution */}
      <section className="space-y-4">
        <div>
          <h3 className="text-lg font-semibold">Aura Distribution</h3>
          <p className="text-sm text-muted-foreground">
            Your aura reflects your magical affinity. Distribute 100 points among the three aspects.
          </p>
        </div>

        {affinitiesLoading ? (
          <div className="space-y-4">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-16 animate-pulse rounded bg-muted" />
            ))}
          </div>
        ) : (
          <div className="space-y-6">
            {(['celestial', 'primal', 'abyssal'] as const).map((affinityType) => {
              const style = getAffinityStyle(affinityType);
              const Icon = style.icon;
              const value =
                affinityType === 'celestial'
                  ? auraCelestial
                  : affinityType === 'primal'
                    ? auraPrimal
                    : auraAbyssal;
              const affinity = affinities?.find((a) => a.affinity_type === affinityType);

              return (
                <div
                  key={affinityType}
                  className={cn('rounded-lg border p-4', style.bgClass, style.borderClass)}
                >
                  <div className="mb-3 flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Icon className={cn('h-5 w-5', style.textClass)} />
                      <span className="font-medium capitalize">{affinityType}</span>
                    </div>
                    <span className={cn('text-lg font-bold', style.textClass)}>{value}%</span>
                  </div>
                  <Slider
                    value={[value]}
                    min={0}
                    max={100}
                    step={1}
                    onValueChange={([v]) => handleAuraChange(affinityType, v)}
                    className={style.sliderClass}
                  />
                  {affinity && (
                    <p className="mt-2 text-xs text-muted-foreground">{affinity.description}</p>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </section>

      {/* Gift Selection */}
      <section className="space-y-4">
        <div>
          <h3 className="text-lg font-semibold">Starting Gift</h3>
          <p className="text-sm text-muted-foreground">
            Choose your initial magical gift. This grants access to unique powers.
          </p>
        </div>

        {giftsLoading ? (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-40 animate-pulse rounded-lg bg-muted" />
            ))}
          </div>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {gifts?.map((gift) => {
              const style = getAffinityStyle(
                affinities?.find((a) => a.id === gift.affinity)?.affinity_type ?? ''
              );
              const isSelected = draftData.selected_gift_id === gift.id;

              return (
                <Card
                  key={gift.id}
                  className={cn(
                    'cursor-pointer transition-all',
                    isSelected && 'ring-2 ring-primary',
                    !isSelected && 'hover:ring-1 hover:ring-primary/50'
                  )}
                  onClick={() => handleGiftSelect(gift)}
                >
                  <CardHeader className="pb-2">
                    <div className="flex items-center justify-between">
                      <CardTitle className="text-base">{gift.name}</CardTitle>
                      {isSelected && <CheckCircle2 className="h-5 w-5 text-primary" />}
                    </div>
                    <span className={cn('text-xs', style.textClass)}>{gift.affinity_name}</span>
                  </CardHeader>
                  <CardContent>
                    <CardDescription className="line-clamp-3">{gift.description}</CardDescription>
                    <p className="mt-2 text-xs text-muted-foreground">
                      {gift.power_count} power{gift.power_count !== 1 ? 's' : ''}
                    </p>
                  </CardContent>
                </Card>
              );
            })}
            {(!gifts || gifts.length === 0) && (
              <Card>
                <CardContent className="py-8">
                  <p className="text-center text-sm text-muted-foreground">No gifts available.</p>
                </CardContent>
              </Card>
            )}
          </div>
        )}
      </section>

      {/* Resonance Selection */}
      <section className="space-y-4">
        <div>
          <h3 className="text-lg font-semibold">Personal Resonances</h3>
          <p className="text-sm text-muted-foreground">
            Select up to {maxResonances} resonances that define your magical signature. (
            {selectedResonanceIds.length}/{maxResonances} selected)
          </p>
        </div>

        {resonancesLoading ? (
          <div className="flex flex-wrap gap-2">
            {[1, 2, 3, 4, 5, 6].map((i) => (
              <div key={i} className="h-10 w-24 animate-pulse rounded bg-muted" />
            ))}
          </div>
        ) : (
          <div className="flex flex-wrap gap-2">
            {resonances?.map((resonance) => {
              const isSelected = selectedResonanceIds.includes(resonance.id);
              const isDisabled = !isSelected && selectedResonanceIds.length >= maxResonances;
              const style = getAffinityStyle(
                affinities?.find((a) => a.id === resonance.default_affinity)?.affinity_type ?? ''
              );

              return (
                <Button
                  key={resonance.id}
                  variant={isSelected ? 'default' : 'outline'}
                  size="sm"
                  disabled={isDisabled}
                  onClick={() => handleResonanceToggle(resonance)}
                  className={cn(
                    isSelected && style.bgClass,
                    isDisabled && 'cursor-not-allowed opacity-50'
                  )}
                  title={resonance.description}
                >
                  {resonance.name}
                </Button>
              );
            })}
            {(!resonances || resonances.length === 0) && (
              <p className="text-sm text-muted-foreground">No resonances available.</p>
            )}
          </div>
        )}
      </section>

      {/* Anima Ritual */}
      <section className="space-y-4">
        <div>
          <h3 className="text-lg font-semibold">Anima Ritual</h3>
          <p className="text-sm text-muted-foreground">
            Choose how your character recovers anima (magical energy) and describe your personal
            ritual.
          </p>
        </div>

        {ritualTypesLoading ? (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-24 animate-pulse rounded-lg bg-muted" />
            ))}
          </div>
        ) : (
          <>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {ritualTypes?.map((ritualType) => {
                const isSelected = draftData.selected_ritual_type_id === ritualType.id;

                return (
                  <Card
                    key={ritualType.id}
                    className={cn(
                      'cursor-pointer transition-all',
                      isSelected && 'ring-2 ring-primary',
                      !isSelected && 'hover:ring-1 hover:ring-primary/50'
                    )}
                    onClick={() => handleRitualTypeSelect(ritualType)}
                  >
                    <CardHeader className="pb-2">
                      <div className="flex items-center justify-between">
                        <CardTitle className="text-base">{ritualType.name}</CardTitle>
                        {isSelected && <CheckCircle2 className="h-5 w-5 text-primary" />}
                      </div>
                      <span className="text-xs text-muted-foreground">
                        {ritualType.category_display}
                      </span>
                    </CardHeader>
                    <CardContent>
                      <CardDescription className="line-clamp-2">
                        {ritualType.description}
                      </CardDescription>
                    </CardContent>
                  </Card>
                );
              })}
              {(!ritualTypes || ritualTypes.length === 0) && (
                <Card>
                  <CardContent className="py-8">
                    <p className="text-center text-sm text-muted-foreground">
                      No ritual types available.
                    </p>
                  </CardContent>
                </Card>
              )}
            </div>

            {draftData.selected_ritual_type_id && (
              <div className="space-y-2">
                <Label htmlFor="ritual-description">Your Personal Ritual</Label>
                <Textarea
                  id="ritual-description"
                  value={draftData.anima_ritual_description ?? ''}
                  onChange={(e) => handleRitualDescriptionChange(e.target.value)}
                  placeholder="Describe how your character performs this ritual..."
                  rows={3}
                  className="resize-y"
                />
                <p className="text-xs text-muted-foreground">
                  How does your character specifically perform this type of ritual?
                </p>
              </div>
            )}
          </>
        )}
      </section>

      {/* The Glimpse (Optional) */}
      <section className="space-y-4">
        <div>
          <h3 className="text-lg font-semibold">The Glimpse (Optional)</h3>
          <p className="text-sm text-muted-foreground">
            Describe the moment your character first awakened to magic. This can be filled in later.
          </p>
        </div>

        <div className="space-y-2">
          <Label htmlFor="glimpse-story">Your Awakening Story</Label>
          <Textarea
            id="glimpse-story"
            value={draftData.glimpse_story ?? ''}
            onChange={(e) => handleGlimpseStoryChange(e.target.value)}
            placeholder="The first time you glimpsed the magical world..."
            rows={4}
            className="resize-y"
          />
        </div>
      </section>
    </motion.div>
  );
}

/**
 * Stage 7: Magic
 *
 * REDESIGNED: Build-your-own magic system.
 *
 * Players now CREATE their magical identity:
 * - Design a custom Gift (affinity + resonances)
 * - Build Techniques within that Gift
 * - Configure their Anima Ritual (stat + skill + resonance)
 * - Set Aura distribution
 * - Optional Glimpse story
 */

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Slider } from '@/components/ui/slider';
import { Textarea } from '@/components/ui/textarea';
import { cn } from '@/lib/utils';
import { motion } from 'framer-motion';
import { Moon, Plus, Sparkles, Sun, Trash2, TreePine } from 'lucide-react';
import { useState } from 'react';
import {
  useAffinities,
  useDeleteDraftTechnique,
  useDraftGifts,
  useResonances,
  useUpdateDraft,
} from '../queries';
import type { AffinityType, CharacterDraft } from '../types';
import { AFFINITY_TYPES } from '../types';
import { AnimaRitualForm, GiftDesigner, TechniqueBuilder } from './magic';

interface MagicStageProps {
  draft: CharacterDraft;
}

const AURA_TOTAL = 100;
const DEFAULT_AURA = 34;

type MagicView = 'overview' | 'gift-designer' | 'technique-builder';

export function MagicStage({ draft }: MagicStageProps) {
  const updateDraft = useUpdateDraft();
  const deleteDraftTechnique = useDeleteDraftTechnique();
  const { data: affinities, isLoading: affinitiesLoading } = useAffinities();
  const { data: resonances } = useResonances();

  const draftData = draft.draft_data;

  // Fetch draft gifts (user can only have one during CG)
  const { data: draftGifts, isLoading: giftLoading } = useDraftGifts();
  const draftGift = draftGifts?.[0] ?? null;

  // Helper to get affinity name from ID
  const getAffinityName = (affinityId: number) => {
    const affinity = affinities?.find((a) => a.id === affinityId);
    return affinity?.name ?? 'Unknown';
  };

  // Helper to get resonance name from ID
  const getResonanceName = (resonanceId: number) => {
    const resonance = resonances?.find((r) => r.id === resonanceId);
    return resonance?.name ?? 'Unknown';
  };

  // Helper to calculate tier from level
  const getTier = (level: number) => Math.ceil(level / 5);

  const [currentView, setCurrentView] = useState<MagicView>('overview');

  // Aura values
  const auraCelestial = draftData.aura_celestial ?? DEFAULT_AURA;
  const auraPrimal = draftData.aura_primal ?? DEFAULT_AURA;
  const auraAbyssal = draftData.aura_abyssal ?? AURA_TOTAL - DEFAULT_AURA * 2;

  const getAffinityStyle = (type: AffinityType | string) => {
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

  const handleAuraChange = (affinity: AffinityType, newValue: number) => {
    const current = { celestial: auraCelestial, primal: auraPrimal, abyssal: auraAbyssal };
    const oldValue = current[affinity];
    const diff = newValue - oldValue;

    const others = AFFINITY_TYPES.filter((a) => a !== affinity);
    const otherSum = others.reduce((sum, a) => sum + current[a], 0);

    const newValues = { ...current, [affinity]: newValue };

    if (otherSum > 0 && diff !== 0) {
      others.forEach((other) => {
        const proportion = current[other] / otherSum;
        const adjustment = Math.round(diff * proportion);
        newValues[other] = Math.max(0, current[other] - adjustment);
      });

      const total = Object.values(newValues).reduce((sum, v) => sum + v, 0);
      if (total !== AURA_TOTAL) {
        const largerOther = newValues[others[0]] >= newValues[others[1]] ? others[0] : others[1];
        newValues[largerOther] += AURA_TOTAL - total;
        newValues[largerOther] = Math.max(0, newValues[largerOther]);
      }
    } else if (diff !== 0) {
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

  const handleGiftCreated = () => {
    // Draft gift is already saved via API, just go back to overview
    // The useDraftGifts query will automatically pick it up
    setCurrentView('overview');
  };

  const handleTechniqueCreated = () => {
    // Technique is already saved via API, just go back to overview
    setCurrentView('overview');
  };

  const handleDeleteTechnique = async (techniqueId: number) => {
    if (!window.confirm('Delete this technique?')) return;
    await deleteDraftTechnique.mutateAsync(techniqueId);
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

  // Render different views
  if (currentView === 'gift-designer') {
    return (
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="space-y-8"
      >
        <GiftDesigner
          onGiftCreated={handleGiftCreated}
          onCancel={() => setCurrentView('overview')}
        />
      </motion.div>
    );
  }

  if (currentView === 'technique-builder' && draftGift) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="space-y-8"
      >
        <TechniqueBuilder
          giftId={draftGift.id}
          existingTechniques={draftGift.techniques}
          onTechniqueCreated={handleTechniqueCreated}
          onCancel={() => setCurrentView('overview')}
        />
      </motion.div>
    );
  }

  // Main overview
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
          Design your character's magical identity. Create a unique gift and build techniques.
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
            {AFFINITY_TYPES.map((affinityType) => {
              const style = getAffinityStyle(affinityType);
              const Icon = style.icon;
              const value =
                affinityType === 'celestial'
                  ? auraCelestial
                  : affinityType === 'primal'
                    ? auraPrimal
                    : auraAbyssal;
              const affinity = affinities?.find((a) => a.name.toLowerCase() === affinityType);

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

      {/* Gift Section */}
      <section className="space-y-4">
        <div>
          <h3 className="text-lg font-semibold">Your Gift</h3>
          <p className="text-sm text-muted-foreground">
            Design a magical gift that defines your character's powers.
          </p>
        </div>

        {giftLoading ? (
          <div className="h-40 animate-pulse rounded-lg bg-muted" />
        ) : draftGift ? (
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center justify-between">
                <span>{draftGift.name}</span>
                <span
                  className={cn(
                    'text-sm',
                    getAffinityStyle(getAffinityName(draftGift.affinity).toLowerCase()).textClass
                  )}
                >
                  {getAffinityName(draftGift.affinity)}
                </span>
              </CardTitle>
              <CardDescription>{draftGift.description || 'No description'}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <Label className="text-xs text-muted-foreground">Resonances</Label>
                <div className="mt-1 flex flex-wrap gap-1">
                  {draftGift.resonances.map((resonanceId) => (
                    <span key={resonanceId} className="rounded bg-muted px-2 py-1 text-xs">
                      {getResonanceName(resonanceId)}
                    </span>
                  ))}
                </div>
              </div>

              {/* Techniques List */}
              <div>
                <div className="flex items-center justify-between">
                  <Label className="text-xs text-muted-foreground">
                    Techniques ({draftGift.techniques.length})
                  </Label>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setCurrentView('technique-builder')}
                  >
                    <Plus className="mr-1 h-3 w-3" />
                    Add Technique
                  </Button>
                </div>
                {draftGift.techniques.length > 0 ? (
                  <div className="mt-2 space-y-2">
                    {draftGift.techniques.map((technique) => (
                      <div
                        key={technique.id}
                        className="flex items-center justify-between rounded border p-2"
                      >
                        <div>
                          <span className="font-medium">{technique.name}</span>
                          <span className="ml-2 text-xs text-muted-foreground">
                            Lvl {technique.level} - Tier {getTier(technique.level)}
                          </span>
                        </div>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleDeleteTechnique(technique.id)}
                        >
                          <Trash2 className="h-4 w-4 text-destructive" />
                        </Button>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="mt-2 text-sm text-muted-foreground">
                    No techniques yet. Add techniques to define your gift's abilities.
                  </p>
                )}
              </div>
            </CardContent>
          </Card>
        ) : (
          <Card className="border-dashed">
            <CardContent className="flex flex-col items-center justify-center py-8">
              <Sparkles className="mb-2 h-8 w-8 text-muted-foreground" />
              <p className="mb-4 text-center text-sm text-muted-foreground">
                You haven't designed a gift yet. Create one to define your magical identity.
              </p>
              <Button onClick={() => setCurrentView('gift-designer')}>
                <Plus className="mr-2 h-4 w-4" />
                Design Your Gift
              </Button>
            </CardContent>
          </Card>
        )}
      </section>

      {/* Anima Ritual Section */}
      <section className="space-y-4">
        <AnimaRitualForm />
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

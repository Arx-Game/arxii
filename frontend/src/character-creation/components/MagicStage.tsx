/**
 * Stage 7: Magic
 *
 * Simplified cantrip-based magic selection.
 *
 * All new characters pick a starting cantrip. Returning players
 * (has_existing_characters) also see an advanced section where they can
 * describe a custom gift, motif, and glimpse story.
 */

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { motion } from 'framer-motion';
import { ChevronDown } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { useCantrips, useCGExplanations, useUpdateDraft } from '../queries';
import type { CharacterDraft } from '../types';
import { CantripSelector } from './magic';

interface MagicStageProps {
  draft: CharacterDraft;
  onRegisterBeforeLeave?: (check: () => Promise<boolean>) => void;
}

interface MagicFormValues {
  custom_gift_name: string;
  custom_gift_description: string;
  motif_description: string;
  glimpse_story: string;
}

export function MagicStage({ draft, onRegisterBeforeLeave }: MagicStageProps) {
  const updateDraft = useUpdateDraft();
  const { data: copy } = useCGExplanations();
  const { data: cantrips, isLoading: cantripsLoading } = useCantrips();

  const draftData = draft.draft_data;

  const [advancedOpen, setAdvancedOpen] = useState(false);

  const { register, getValues, formState } = useForm<MagicFormValues>({
    defaultValues: {
      custom_gift_name: draftData.custom_gift_name ?? '',
      custom_gift_description: draftData.custom_gift_description ?? '',
      motif_description: draftData.motif_description ?? '',
      glimpse_story: draftData.glimpse_story ?? '',
    },
  });

  const saveFormFields = useCallback(async () => {
    if (!formState.isDirty) return true;
    try {
      await updateDraft.mutateAsync({
        draftId: draft.id,
        data: {
          draft_data: {
            ...draft.draft_data,
            ...getValues(),
          },
        },
      });
      return true;
    } catch {
      return window.confirm('Failed to save. Discard changes and continue?');
    }
  }, [draft.id, draft.draft_data, updateDraft, formState.isDirty, getValues]);

  useEffect(() => {
    if (onRegisterBeforeLeave) {
      onRegisterBeforeLeave(saveFormFields);
    }
  }, [onRegisterBeforeLeave, saveFormFields]);

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -20 }}
      transition={{ duration: 0.3 }}
      className="space-y-8"
    >
      {/* Heading */}
      <div>
        <h2 className="theme-heading text-2xl font-bold">{copy?.magic_heading ?? ''}</h2>
        <p className="mt-2 text-muted-foreground">Choose a starting magical ability.</p>
      </div>

      {/* Cantrip selector */}
      <section className="space-y-4">
        {cantripsLoading ? (
          <div className="h-40 animate-pulse rounded-lg bg-muted" />
        ) : cantrips && cantrips.length > 0 ? (
          <CantripSelector draft={draft} cantrips={cantrips} />
        ) : (
          <p className="text-sm text-muted-foreground">No cantrips available.</p>
        )}
      </section>

      {/* Advanced section for returning players */}
      {draft.has_existing_characters && (
        <section className="space-y-4">
          <Button
            variant="ghost"
            className="flex items-center gap-2 px-0 text-sm font-semibold"
            onClick={() => setAdvancedOpen(!advancedOpen)}
          >
            <ChevronDown
              className={`h-4 w-4 transition-transform duration-200 ${advancedOpen ? 'rotate-180' : ''}`}
            />
            Advanced Magic Options
          </Button>

          {advancedOpen && (
            <div className="space-y-6 pl-2">
              {/* Custom gift name */}
              <div className="max-w-md space-y-2">
                <Label htmlFor="custom-gift-name">Name your gift</Label>
                <Input
                  id="custom-gift-name"
                  {...register('custom_gift_name')}
                  placeholder="A name for your magical gift..."
                  maxLength={100}
                />
              </div>

              {/* Custom gift description */}
              <div className="space-y-2">
                <Label htmlFor="custom-gift-description">Describe your gift</Label>
                <Textarea
                  id="custom-gift-description"
                  {...register('custom_gift_description')}
                  placeholder="Describe your magical gift..."
                  rows={3}
                  className="resize-y"
                />
              </div>

              {/* Motif */}
              <div className="space-y-2">
                <Label htmlFor="motif-description">Motif</Label>
                <Textarea
                  id="motif-description"
                  {...register('motif_description')}
                  placeholder="Describe the aesthetic of your magic..."
                  rows={3}
                  className="resize-y"
                />
              </div>

              {/* The Glimpse */}
              <div className="space-y-2">
                <Label htmlFor="glimpse-story">The Glimpse</Label>
                <Textarea
                  id="glimpse-story"
                  {...register('glimpse_story')}
                  placeholder="The first time you glimpsed the magical world..."
                  rows={4}
                  className="resize-y"
                />
              </div>

              {/* TODO: tradition selector */}
            </div>
          )}
        </section>
      )}
    </motion.div>
  );
}

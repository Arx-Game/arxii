/**
 * Stage 6: Gift
 *
 * Vertical funnel — Tradition → Gift → Techniques → Gift Resonance →
 * Anima Check — with completed steps collapsible. Motif and Glimpse remain
 * always-visible textareas below the funnel, carried over from the old
 * MagicStage advanced section (glimpse redesign is #2427, not this task).
 */

import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { motion } from 'framer-motion';
import { CheckCircle2 } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { useCGExplanations, useResonances, useUpdateDraft } from '../queries';
import type { CharacterDraft } from '../types';
import { AnimaCheckStep } from './gift/AnimaCheckStep';
import { GiftSelector } from './gift/GiftSelector';
import { TechniqueSelector } from './gift/TechniqueSelector';
import { TraditionStep } from './gift/TraditionStep';

interface GiftStageProps {
  draft: CharacterDraft;
  onRegisterBeforeLeave?: (check: () => Promise<boolean>) => void;
}

interface GiftFormValues {
  anima_ritual_name: string;
  motif_description: string;
  glimpse_story: string;
}

type FunnelStepId = 'tradition' | 'gift' | 'techniques' | 'resonance' | 'anima';

const FUNNEL_STEPS: { id: FunnelStepId; label: string }[] = [
  { id: 'tradition', label: 'Tradition' },
  { id: 'gift', label: 'Gift' },
  { id: 'techniques', label: 'Techniques' },
  { id: 'resonance', label: 'Gift Resonance' },
  { id: 'anima', label: 'Anima Check' },
];

function StepLabel({ label, complete }: { label: string; complete: boolean }) {
  return (
    <span className="flex items-center gap-2">
      {complete && <CheckCircle2 className="h-4 w-4 text-green-500" />}
      {label}
    </span>
  );
}

export function GiftStage({ draft, onRegisterBeforeLeave }: GiftStageProps) {
  const updateDraft = useUpdateDraft();
  const { data: copy } = useCGExplanations();
  const { data: resonances = [] } = useResonances();

  const draftData = draft.draft_data;
  const giftId = draftData.selected_gift_id ?? null;
  const selectedResonanceId = draftData.selected_gift_resonance_id ?? null;

  const completion: Record<FunnelStepId, boolean> = {
    tradition: draft.selected_tradition != null,
    gift: giftId != null,
    techniques: (draftData.selected_technique_ids?.length ?? 0) > 0,
    resonance: selectedResonanceId != null,
    anima: draftData.anima_check_stat_id != null && draftData.anima_check_skill_id != null,
  };

  // Open on the first incomplete step (or the last one if every step is done)
  // so returning to this stage lands the player where they left off.
  const [openStep, setOpenStep] = useState<FunnelStepId | ''>(() => {
    const firstIncomplete = FUNNEL_STEPS.find((step) => !completion[step.id]);
    return firstIncomplete?.id ?? FUNNEL_STEPS[FUNNEL_STEPS.length - 1].id;
  });

  const handleSelectResonance = (resonanceId: string) => {
    updateDraft.mutate({
      draftId: draft.id,
      data: {
        draft_data: {
          ...draft.draft_data,
          selected_gift_resonance_id: parseInt(resonanceId, 10),
        },
      },
    });
  };

  const { register, getValues, formState } = useForm<GiftFormValues>({
    defaultValues: {
      anima_ritual_name: draftData.anima_ritual_name ?? '',
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
      <div>
        <h2 className="theme-heading text-2xl font-bold">{copy?.magic_heading ?? 'Gift'}</h2>
        <p className="mt-2 text-muted-foreground">
          {copy?.magic_intro ?? 'Choose your magical tradition, gift, and how your magic works.'}
        </p>
      </div>

      <Accordion
        type="single"
        collapsible
        value={openStep}
        onValueChange={(value) => setOpenStep(value as FunnelStepId | '')}
      >
        <AccordionItem value="tradition">
          <AccordionTrigger>
            <StepLabel label={FUNNEL_STEPS[0].label} complete={completion.tradition} />
          </AccordionTrigger>
          <AccordionContent>
            <TraditionStep draft={draft} />
          </AccordionContent>
        </AccordionItem>

        <AccordionItem value="gift" disabled={!completion.tradition}>
          <AccordionTrigger disabled={!completion.tradition}>
            <StepLabel label={FUNNEL_STEPS[1].label} complete={completion.gift} />
          </AccordionTrigger>
          <AccordionContent>
            <GiftSelector draft={draft} />
          </AccordionContent>
        </AccordionItem>

        <AccordionItem value="techniques" disabled={!completion.gift}>
          <AccordionTrigger disabled={!completion.gift}>
            <StepLabel label={FUNNEL_STEPS[2].label} complete={completion.techniques} />
          </AccordionTrigger>
          <AccordionContent>
            {giftId != null ? (
              <TechniqueSelector draft={draft} giftId={giftId} />
            ) : (
              <p className="text-sm text-muted-foreground">Select a gift first.</p>
            )}
          </AccordionContent>
        </AccordionItem>

        <AccordionItem value="resonance" disabled={!completion.gift}>
          <AccordionTrigger disabled={!completion.gift}>
            <StepLabel label={FUNNEL_STEPS[3].label} complete={completion.resonance} />
          </AccordionTrigger>
          <AccordionContent>
            <div className="max-w-xs space-y-2">
              <Label htmlFor="gift-resonance">Gift Resonance</Label>
              <Select
                value={selectedResonanceId?.toString() ?? ''}
                onValueChange={handleSelectResonance}
              >
                <SelectTrigger id="gift-resonance">
                  <SelectValue placeholder="Select a resonance" />
                </SelectTrigger>
                <SelectContent>
                  {resonances.map((resonance) => (
                    <SelectItem key={resonance.id} value={resonance.id.toString()}>
                      {resonance.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </AccordionContent>
        </AccordionItem>

        <AccordionItem value="anima">
          <AccordionTrigger>
            <StepLabel label={FUNNEL_STEPS[4].label} complete={completion.anima} />
          </AccordionTrigger>
          <AccordionContent>
            <AnimaCheckStep draft={draft} ritualNameField={register('anima_ritual_name')} />
          </AccordionContent>
        </AccordionItem>
      </Accordion>

      {/* Motif + Glimpse — always visible (carried from the old MagicStage advanced
          section; glimpse redesign is #2427, not this task) */}
      <section className="space-y-6">
        <div className="space-y-2">
          <Label htmlFor="motif-description">{copy?.magic_motif_heading ?? 'Motif'}</Label>
          <Textarea
            id="motif-description"
            {...register('motif_description')}
            placeholder="Describe the aesthetic of your magic..."
            rows={3}
            className="resize-y"
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="glimpse-story">{copy?.magic_glimpse_heading ?? 'The Glimpse'}</Label>
          <Textarea
            id="glimpse-story"
            {...register('glimpse_story')}
            placeholder="The first time you glimpsed the magical world..."
            rows={4}
            className="resize-y"
          />
        </div>
      </section>
    </motion.div>
  );
}

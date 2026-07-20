/**
 * Stage 7: Identity
 *
 * Name, concept, quote, personality, and background fields.
 */

import { Input } from '@/components/ui/input';
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
import { useCallback, useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { useCGExplanations, useUpdateDraft, useWorshippedBeings } from '../queries';
import type { CharacterDraft } from '../types';
import { OriginStorySection } from './OriginStorySection';

const NONE_VALUE = 'none';

interface IdentityStageProps {
  draft: CharacterDraft;
  onRegisterBeforeLeave?: (check: () => Promise<boolean>) => (() => void) | void;
}

interface IdentityFormValues {
  first_name: string;
  concept: string;
  quote: string;
  personality: string;
  background: string;
}

export function IdentityStage({ draft, onRegisterBeforeLeave }: IdentityStageProps) {
  const updateDraft = useUpdateDraft();
  const { data: copy } = useCGExplanations();
  const { data: beings } = useWorshippedBeings();
  const draftData = draft.draft_data;

  const handleWorshipChange = (
    field: 'public_worship_id' | 'secret_worship_id',
    value: number | null
  ) => {
    updateDraft.mutate({
      draftId: draft.id,
      data: { [field]: value },
    });
  };

  const { register, watch, getValues, reset, formState } = useForm<IdentityFormValues>({
    defaultValues: {
      first_name: draftData.first_name ?? '',
      concept: draftData.concept ?? '',
      quote: draftData.quote ?? '',
      personality: draftData.personality ?? '',
      background: draftData.background ?? '',
    },
  });

  const saveFields = useCallback(async () => {
    if (!formState.isDirty) return true;

    try {
      await updateDraft.mutateAsync({
        draftId: draft.id,
        data: {
          draft_data: {
            ...getValues(),
          },
        },
      });
      // Clear isDirty so a re-registered save doesn't resend unchanged values.
      reset(getValues());
      return true;
    } catch {
      return window.confirm('Failed to save. Discard changes and continue?');
    }
  }, [draft.id, updateDraft, formState.isDirty, getValues, reset]);

  useEffect(() => {
    if (!onRegisterBeforeLeave) return;
    // Return the unregister as cleanup (2026-07 audit): without it, an
    // unmounted stage's save closure stayed registered and re-fired on every
    // later navigation, PATCHing stale values over newer edits.
    return onRegisterBeforeLeave(saveFields) ?? undefined;
  }, [onRegisterBeforeLeave, saveFields]);

  const localFirstName = watch('first_name');
  const familyName = draft.family?.name ?? '';
  const fullNamePreview = localFirstName
    ? familyName
      ? `${localFirstName} ${familyName}`
      : localFirstName
    : '';

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -20 }}
      transition={{ duration: 0.3 }}
      className="space-y-8"
    >
      <div>
        <h2 className="theme-heading text-2xl font-bold">{copy?.identity_heading ?? ''}</h2>
        <p className="mt-2 text-muted-foreground">{copy?.identity_intro ?? ''}</p>
      </div>

      {/* Name */}
      <section className="space-y-4">
        <h3 className="theme-heading text-lg font-semibold">Character Name</h3>
        <div className="max-w-md space-y-2">
          <Label htmlFor="first-name">First Name</Label>
          <Input
            id="first-name"
            {...register('first_name')}
            placeholder="Enter first name"
            maxLength={20}
          />
          <p className="text-xs text-muted-foreground">
            2-20 characters, letters only, first letter will be capitalized.
          </p>
          {fullNamePreview && (
            <p className="mt-2 text-sm">
              Full name: <span className="font-semibold">{fullNamePreview}</span>
            </p>
          )}
        </div>
      </section>

      {/* Concept */}
      <section className="space-y-4">
        <h3 className="theme-heading text-lg font-semibold">Concept</h3>
        <div className="max-w-md space-y-2">
          <Label htmlFor="concept">Character Concept</Label>
          <Input
            id="concept"
            {...register('concept')}
            placeholder="A short tagline for your character..."
            maxLength={255}
          />
          <p className="text-xs text-muted-foreground">
            A brief archetype or tagline (e.g., &quot;Ruthless pragmatist with a hidden
            heart&quot;).
          </p>
        </div>
      </section>

      {/* Quote */}
      <section className="space-y-4">
        <h3 className="theme-heading text-lg font-semibold">Quote</h3>
        <div className="max-w-md space-y-2">
          <Label htmlFor="quote">Character Quote</Label>
          <Input
            id="quote"
            {...register('quote')}
            placeholder="A signature quote or motto..."
            maxLength={500}
          />
          <p className="text-xs text-muted-foreground">
            A saying, motto, or line that captures your character&apos;s voice.
          </p>
        </div>
      </section>

      {/* Personality */}
      <section className="space-y-4">
        <h3 className="theme-heading text-lg font-semibold">Personality</h3>
        <div className="space-y-2">
          <Label htmlFor="personality">Personality Traits</Label>
          <Textarea
            id="personality"
            {...register('personality')}
            placeholder="Describe your character's personality..."
            rows={3}
            className="resize-y"
          />
          <p className="text-xs text-muted-foreground">
            How does your character think, feel, and behave?
          </p>
        </div>
      </section>

      {/* Origin Story (#2478) — replaces free-text Background */}
      <OriginStorySection draft={draft} />

      {/* Worship (#2355) */}
      <section className="space-y-4">
        <h3 className="theme-heading text-lg font-semibold">Worship</h3>
        <div className="max-w-md space-y-2">
          <Label htmlFor="public-worship">Public Worship</Label>
          <Select
            value={draft.public_worship ? String(draft.public_worship.id) : NONE_VALUE}
            onValueChange={(value) =>
              handleWorshipChange('public_worship_id', value === NONE_VALUE ? null : Number(value))
            }
          >
            <SelectTrigger id="public-worship">
              <SelectValue placeholder="Choose a being (optional)" />
            </SelectTrigger>
            <SelectContent className="max-h-60 overflow-y-auto">
              <SelectItem value={NONE_VALUE}>Unaffiliated</SelectItem>
              {(beings ?? []).map((being) => (
                <SelectItem key={being.id} value={String(being.id)}>
                  {being.name} ({being.tradition_name})
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <p className="text-xs text-muted-foreground">
            The god, spirit, or power your character openly worships. Optional.
          </p>
        </div>
        <div className="max-w-md space-y-2">
          <Label htmlFor="secret-worship">Secret Worship</Label>
          <Select
            value={draft.secret_worship ? String(draft.secret_worship.id) : NONE_VALUE}
            onValueChange={(value) =>
              handleWorshipChange('secret_worship_id', value === NONE_VALUE ? null : Number(value))
            }
          >
            <SelectTrigger id="secret-worship">
              <SelectValue placeholder="None — my faith is what it appears" />
            </SelectTrigger>
            <SelectContent className="max-h-60 overflow-y-auto">
              <SelectItem value={NONE_VALUE}>None</SelectItem>
              {(beings ?? []).map((being) => (
                <SelectItem key={being.id} value={String(being.id)}>
                  {being.name} ({being.tradition_name})
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <p className="text-xs text-muted-foreground">
            The truth behind the front. Choosing one mints a Secret others might uncover.
          </p>
        </div>
      </section>
    </motion.div>
  );
}

/**
 * Stage 9: Identity (#3630).
 *
 * Name, concept, quote and personality as writing fields on the hairline;
 * worship stays a native select (the catalog is long). The record rail lists
 * the choices made so far, including the full-name preview this stage
 * computes; the one mechanically-loaded explanation (a secret worship mints
 * a Secret others might uncover) lives in the margin rather than under a
 * section heading (Decision 8).
 */

import { useCallback, useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { ChapterLeaf, Field, Marginalia, Note, RecordRail } from '../folio';
import { useCGExplanations, useUpdateDraft, useWorshippedBeings } from '../queries';
import type { CharacterDraft } from '../types';
import { Stage } from '../types';
import { composeFullName } from '../utils';

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
  const fullNamePreview = composeFullName(localFirstName, familyName, '');

  const rail = (
    <>
      <RecordRail
        rows={[
          { label: 'Origin', value: draft.selected_area?.name },
          { label: 'Species', value: draft.selected_species?.name },
          { label: 'Family', value: draft.family?.name },
          // Absent (not "not yet chosen") until a first name exists (#3630).
          ...(fullNamePreview ? [{ label: 'Name', value: fullNamePreview }] : []),
          { label: 'Public worship', value: draft.public_worship?.name },
          { label: 'Secret worship', value: draft.secret_worship?.name },
        ]}
        ledger="Stage 9 of 11"
      />
      <Marginalia id="note-identity">
        <Note lead="Secret worship">
          The truth behind the front. Choosing one mints a Secret others might uncover.
        </Note>
      </Marginalia>
    </>
  );

  return (
    <ChapterLeaf
      stage={Stage.IDENTITY}
      title={copy?.identity_heading ?? 'Name & Identity'}
      intro={copy?.identity_intro}
      aside={rail}
    >
      <h2 className="section-h">{copy?.identity_name_heading ?? 'Name'}</h2>
      <Field
        id="first_name"
        label="First Name"
        hint="2-20 characters, letters only, first letter will be capitalized."
      >
        <input
          id="first_name"
          type="text"
          {...register('first_name')}
          placeholder="Enter first name"
          maxLength={20}
        />
      </Field>

      <h2 className="section-h">{copy?.identity_concept_heading ?? 'Concept'}</h2>
      <Field
        id="concept"
        label="Character Concept"
        hint="A brief archetype or tagline (e.g., “Ruthless pragmatist with a hidden heart”)."
      >
        <input
          id="concept"
          type="text"
          {...register('concept')}
          placeholder="A short tagline for your character..."
          maxLength={255}
        />
      </Field>

      <h2 className="section-h">{copy?.identity_quote_heading ?? 'Quote'}</h2>
      <Field
        id="quote"
        label="Character Quote"
        hint="A saying, motto, or line that captures your character’s voice."
      >
        <input
          id="quote"
          type="text"
          {...register('quote')}
          placeholder="A signature quote or motto..."
          maxLength={500}
        />
      </Field>

      <h2 className="section-h">{copy?.identity_personality_heading ?? 'Personality'}</h2>
      <Field
        id="personality"
        label="Personality Traits"
        hint="How does your character think, feel, and behave?"
      >
        <textarea
          id="personality"
          rows={6}
          {...register('personality')}
          placeholder="Describe your character's personality..."
        />
      </Field>

      <h2 className="section-h">{copy?.identity_worship_heading ?? 'Worship'}</h2>
      <Field
        id="public_worship"
        label="Public worship"
        hint="The god, spirit, or power your character openly worships. Optional."
      >
        <select
          id="public_worship"
          value={draft.public_worship?.id ?? ''}
          onChange={(e) =>
            handleWorshipChange(
              'public_worship_id',
              e.target.value === '' ? null : Number(e.target.value)
            )
          }
        >
          <option value="">Unaffiliated</option>
          {(beings ?? []).map((being) => (
            <option key={being.id} value={being.id}>
              {being.name} ({being.tradition_name})
            </option>
          ))}
        </select>
      </Field>
      <Field id="secret_worship" label="Secret worship">
        <select
          id="secret_worship"
          value={draft.secret_worship?.id ?? ''}
          onChange={(e) =>
            handleWorshipChange(
              'secret_worship_id',
              e.target.value === '' ? null : Number(e.target.value)
            )
          }
        >
          <option value="">None</option>
          {(beings ?? []).map((being) => (
            <option key={being.id} value={being.id}>
              {being.name} ({being.tradition_name})
            </option>
          ))}
        </select>
      </Field>
    </ChapterLeaf>
  );
}

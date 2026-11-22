/**
 * AnimaRitualEditDialog — Dialog for authoring/editing a player's anima ritual.
 *
 * Submits via PATCH to /api/magic/rituals/{id}/ (usePatchRitual).
 *
 * Backend gap (Phase 9): RitualViewSet is ReadOnlyModelViewSet — PATCH returns
 * 405 until the backend is updated to accept partial updates. The RitualSerializer
 * does expose check_config fields (stat, skill, check_type, etc.) but pre-population
 * from server data was deferred. The form still submits FK ids for these fields via
 * AnimaRitualPatchBody.
 *
 * Stat/Skill/CheckType pickers are plain number inputs for now — dedicated FK
 * picker components do not yet exist for these model types. Flag for follow-up.
 *
 * Pattern mirrors RitualPerformDialog.tsx.
 */

import { useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { extractErrorMessage } from '@/lib/errors';
import { useAnimaRitualChoices, usePatchRitual, useSetUpAnimaRitual } from '@/rituals/queries';
import type { RitualWithSchema } from '@/rituals/types';
import { AnimaRitualAttuneDialog } from './AnimaRitualAttuneDialog';
import { AnimaRitualPillPicker } from './AnimaRitualPillPicker';
import { affinityInkClass } from './affinityInk';

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface AnimaRitualEditDialogProps {
  ritual: RitualWithSchema;
  /** The character whose ritual this is; the resonance picks are read and written for her. */
  characterSheetId: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSuccess?: () => void;
}

// ---------------------------------------------------------------------------
// Form state
// ---------------------------------------------------------------------------

interface FormState {
  name: string;
  description: string;
  narrative_prose: string;
  /** FK id for traits.Trait (stat) — pending proper picker (Phase 10) */
  stat_id: string;
  /** FK id for skills.Skill — pending proper picker (Phase 10) */
  skill_id: string;
  /** FK id for skills.Specialization — optional */
  specialization_id: string;
  /** FK id for checks.CheckType */
  check_type_id: string;
  target_difficulty_level: string;
}

function initFormState(ritual: RitualWithSchema): FormState {
  return {
    name: ritual.name ?? '',
    description: ritual.description ?? '',
    narrative_prose: ritual.narrative_prose ?? '',
    stat_id: '',
    skill_id: '',
    specialization_id: '',
    check_type_id: '',
    target_difficulty_level: '0',
  };
}

// ---------------------------------------------------------------------------
// Validation
// ---------------------------------------------------------------------------

function isValid(form: FormState): boolean {
  return (
    form.name.trim().length > 0 &&
    form.stat_id.trim().length > 0 &&
    form.skill_id.trim().length > 0 &&
    form.check_type_id.trim().length > 0
  );
}

// ---------------------------------------------------------------------------
// The two resonance picks (#5280)
// ---------------------------------------------------------------------------

/**
 * While the ritual has no resonance: two pill pickers and a free "Set resonances". Once set the
 * picks are read-only and "Attune" opens the paid change.
 */
function AnimaRitualResonances({ characterSheetId }: { characterSheetId: number }) {
  const { data: choices, isError, error } = useAnimaRitualChoices(characterSheetId);
  const setUp = useSetUpAnimaRitual();
  const [primalId, setPrimalId] = useState<number | null>(null);
  // undefined until she picks: the outward slot starts with nothing selected, "None" included.
  const [outwardId, setOutwardId] = useState<number | null | undefined>(undefined);
  const [attuneOpen, setAttuneOpen] = useState(false);

  if (isError) {
    return (
      <p role="alert" className="text-sm text-destructive" data-testid="anima-ritual-choices-error">
        {extractErrorMessage(error, 'Failed to load your ritual resonances')}
      </p>
    );
  }
  if (!choices) return null;

  if (choices.locked) {
    return (
      <div className="space-y-3" data-testid="anima-ritual-resonances-locked">
        <div className="flex flex-wrap gap-4">
          <div className="min-w-0 flex-1 basis-56">
            <span className="block text-sm font-medium">What you feel</span>
            <span
              className={`mt-1 block rounded-md border border-dashed px-3 py-2 text-sm ${affinityInkClass(choices.primal_pick?.affinity_name)}`}
            >
              {choices.primal_pick?.name ?? 'None'}
            </span>
          </div>
          <div className="min-w-0 flex-1 basis-56">
            <span className="block text-sm font-medium">What it does to them</span>
            <span
              className={`mt-1 block rounded-md border border-dashed px-3 py-2 text-sm ${affinityInkClass(choices.outward_pick?.affinity_name)}`}
            >
              {choices.outward_pick?.name ?? 'None'}
            </span>
          </div>
        </div>
        <Button
          type="button"
          variant="outline"
          onClick={() => setAttuneOpen(true)}
          data-testid="anima-ritual-attune-button"
        >
          Attune
        </Button>
        {attuneOpen && (
          <AnimaRitualAttuneDialog
            characterSheetId={characterSheetId}
            choices={choices}
            open={attuneOpen}
            onOpenChange={setAttuneOpen}
          />
        )}
      </div>
    );
  }

  const setUpError = setUp.isError
    ? extractErrorMessage(setUp.error, 'Failed to set your ritual resonances')
    : null;

  return (
    <div className="space-y-3" data-testid="anima-ritual-resonances-unset">
      {setUpError && (
        <p role="alert" className="text-sm text-destructive" data-testid="anima-ritual-setup-error">
          {setUpError}
        </p>
      )}
      <div className="flex flex-wrap gap-4">
        <AnimaRitualPillPicker
          label="What you feel when you perform it"
          hint="Primal resonances you hold"
          resonances={choices.primal}
          selectedId={primalId}
          onSelect={setPrimalId}
          disabled={setUp.isPending}
          testId="setup-primal-picker"
        />
        <AnimaRitualPillPicker
          label="What it does to the other person"
          hint="Celestial and Abyssal resonances you hold"
          resonances={choices.outward}
          selectedId={outwardId}
          onSelect={setOutwardId}
          allowNone
          disabled={setUp.isPending}
          testId="setup-outward-picker"
        />
      </div>
      <Button
        type="button"
        disabled={(primalId === null && !outwardId) || setUp.isPending}
        onClick={() =>
          setUp.mutate({
            character_sheet_id: characterSheetId,
            primal_resonance_id: primalId,
            outward_resonance_id: outwardId ?? null,
          })
        }
        data-testid="anima-ritual-set-resonances-button"
      >
        Set resonances
      </Button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function AnimaRitualEditDialog({
  ritual,
  characterSheetId,
  open,
  onOpenChange,
  onSuccess,
}: AnimaRitualEditDialogProps) {
  const [form, setForm] = useState<FormState>(() => initFormState(ritual));

  const patchMutation = usePatchRitual();

  function resetForm() {
    setForm(initFormState(ritual));
    patchMutation.reset();
  }

  function handleOpenChange(next: boolean) {
    onOpenChange(next);
    if (!next) resetForm();
  }

  function handleChange(field: keyof FormState, value: string) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();

    const statId = parseInt(form.stat_id, 10);
    const skillId = parseInt(form.skill_id, 10);
    const checkTypeId = parseInt(form.check_type_id, 10);
    const difficulty = parseInt(form.target_difficulty_level, 10);
    const specializationId = form.specialization_id ? parseInt(form.specialization_id, 10) : null;

    patchMutation.mutate(
      {
        id: ritual.id,
        body: {
          name: form.name.trim(),
          description: form.description.trim(),
          narrative_prose: form.narrative_prose.trim(),
          stat_id: Number.isNaN(statId) ? undefined : statId,
          skill_id: Number.isNaN(skillId) ? undefined : skillId,
          check_type_id: Number.isNaN(checkTypeId) ? undefined : checkTypeId,
          target_difficulty_level: Number.isNaN(difficulty) ? 0 : difficulty,
          specialization_id: Number.isNaN(specializationId) ? null : specializationId,
        },
      },
      {
        onSuccess: () => {
          handleOpenChange(false);
          onSuccess?.();
        },
      }
    );
  }

  const canSubmit = isValid(form) && !patchMutation.isPending;
  const errorMessage = patchMutation.isError
    ? extractErrorMessage(patchMutation.error, 'Failed to update ritual')
    : null;

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>Edit Anima Ritual</DialogTitle>
            <DialogDescription>
              Customise your personal anima ritual. All fields marked * are required.
            </DialogDescription>
          </DialogHeader>

          {/* Error banner */}
          {errorMessage && (
            <div
              className="mt-4 rounded-md bg-destructive/10 px-4 py-3 text-sm text-destructive"
              data-testid="anima-ritual-edit-error"
            >
              <p>{errorMessage}</p>
            </div>
          )}

          <div className="mt-4 space-y-4">
            <AnimaRitualResonances characterSheetId={characterSheetId} />

            {/* Name */}
            <div>
              <label htmlFor="anima-ritual-name" className="mb-1 block text-sm font-medium">
                Name *
              </label>
              <input
                id="anima-ritual-name"
                type="text"
                value={form.name}
                onChange={(e) => handleChange('name', e.target.value)}
                disabled={patchMutation.isPending}
                data-testid="field-name"
                className="w-full rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                required
              />
            </div>

            {/* Description */}
            <div>
              <label htmlFor="anima-ritual-description" className="mb-1 block text-sm font-medium">
                Description
              </label>
              <textarea
                id="anima-ritual-description"
                value={form.description}
                onChange={(e) => handleChange('description', e.target.value)}
                disabled={patchMutation.isPending}
                data-testid="field-description"
                rows={2}
                className="w-full rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              />
            </div>

            {/* Narrative prose */}
            <div>
              <label
                htmlFor="anima-ritual-narrative-prose"
                className="mb-1 block text-sm font-medium"
              >
                Narrative Prose
              </label>
              <textarea
                id="anima-ritual-narrative-prose"
                value={form.narrative_prose}
                onChange={(e) => handleChange('narrative_prose', e.target.value)}
                disabled={patchMutation.isPending}
                data-testid="field-narrative-prose"
                rows={3}
                className="w-full rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              />
            </div>

            {/* Stat (FK id) — TODO Phase 10: replace with TraitPicker component */}
            <div>
              <label htmlFor="anima-ritual-stat-id" className="mb-1 block text-sm font-medium">
                Stat ID *{' '}
                <span className="text-xs text-muted-foreground">
                  (pending proper picker: enter the Trait PK for now)
                </span>
              </label>
              <input
                id="anima-ritual-stat-id"
                type="number"
                min={1}
                value={form.stat_id}
                onChange={(e) => handleChange('stat_id', e.target.value)}
                disabled={patchMutation.isPending}
                data-testid="field-stat-id"
                className="w-full rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                required
              />
            </div>

            {/* Skill (FK id) — TODO Phase 10: replace with SkillPicker component */}
            <div>
              <label htmlFor="anima-ritual-skill-id" className="mb-1 block text-sm font-medium">
                Skill ID *{' '}
                <span className="text-xs text-muted-foreground">
                  (pending proper picker: enter the Skill PK for now)
                </span>
              </label>
              <input
                id="anima-ritual-skill-id"
                type="number"
                min={1}
                value={form.skill_id}
                onChange={(e) => handleChange('skill_id', e.target.value)}
                disabled={patchMutation.isPending}
                data-testid="field-skill-id"
                className="w-full rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                required
              />
            </div>

            {/* Specialization (optional FK id) — TODO Phase 10 */}
            <div>
              <label
                htmlFor="anima-ritual-specialization-id"
                className="mb-1 block text-sm font-medium"
              >
                Specialization ID <span className="text-xs text-muted-foreground">(optional)</span>
              </label>
              <input
                id="anima-ritual-specialization-id"
                type="number"
                min={1}
                value={form.specialization_id}
                onChange={(e) => handleChange('specialization_id', e.target.value)}
                disabled={patchMutation.isPending}
                data-testid="field-specialization-id"
                className="w-full rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              />
            </div>

            {/* Check type (FK id) — TODO Phase 10: replace with CheckTypePicker */}
            <div>
              <label
                htmlFor="anima-ritual-check-type-id"
                className="mb-1 block text-sm font-medium"
              >
                Check Type ID *{' '}
                <span className="text-xs text-muted-foreground">
                  (pending proper picker: enter the CheckType PK for now)
                </span>
              </label>
              <input
                id="anima-ritual-check-type-id"
                type="number"
                min={1}
                value={form.check_type_id}
                onChange={(e) => handleChange('check_type_id', e.target.value)}
                disabled={patchMutation.isPending}
                data-testid="field-check-type-id"
                className="w-full rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                required
              />
            </div>

            {/* Target difficulty */}
            <div>
              <label
                htmlFor="anima-ritual-target-difficulty"
                className="mb-1 block text-sm font-medium"
              >
                Target Difficulty Level
              </label>
              <input
                id="anima-ritual-target-difficulty"
                type="number"
                min={0}
                max={30}
                value={form.target_difficulty_level}
                onChange={(e) => handleChange('target_difficulty_level', e.target.value)}
                disabled={patchMutation.isPending}
                data-testid="field-target-difficulty"
                className="w-full rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              />
            </div>
          </div>

          <DialogFooter className="mt-6">
            <Button
              type="button"
              variant="outline"
              onClick={() => handleOpenChange(false)}
              disabled={patchMutation.isPending}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={!canSubmit} data-testid="anima-ritual-save-button">
              {patchMutation.isPending ? 'Saving…' : 'Save'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

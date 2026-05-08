/**
 * AnimaRitualEditDialog — Dialog for authoring/editing a player's anima ritual.
 *
 * Submits via PATCH to /api/magic/rituals/{id}/ (usePatchRitual).
 *
 * Backend gap (Phase 9): RitualViewSet is ReadOnlyModelViewSet — PATCH returns
 * 405 until the backend is updated to accept partial updates. The RitualSerializer
 * also does not expose scene_action_config fields (stat, skill, check_type, etc.)
 * so those fields cannot be pre-populated from server data until Phase 10 adds
 * them. The form still submits FK ids for these fields via AnimaRitualPatchBody.
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
import { usePatchRitual } from '@/rituals/queries';
import type { RitualWithSchema } from '@/rituals/types';

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface AnimaRitualEditDialogProps {
  ritual: RitualWithSchema;
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
  /** FK id for magic.Resonance — optional */
  resonance_id: string;
  /** FK id for checks.CheckType */
  check_type_id: string;
  target_difficulty: string;
}

function initFormState(ritual: RitualWithSchema): FormState {
  return {
    name: ritual.name ?? '',
    description: ritual.description ?? '',
    narrative_prose: ritual.narrative_prose ?? '',
    stat_id: '',
    skill_id: '',
    specialization_id: '',
    resonance_id: '',
    check_type_id: '',
    target_difficulty: '3',
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
// Error helper
// ---------------------------------------------------------------------------

function extractErrorMessage(error: unknown): string {
  if (error instanceof Error && error.message) return error.message;
  return 'Failed to update ritual';
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function AnimaRitualEditDialog({
  ritual,
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
    const difficulty = parseInt(form.target_difficulty, 10);
    const specializationId = form.specialization_id ? parseInt(form.specialization_id, 10) : null;
    const resonanceId = form.resonance_id ? parseInt(form.resonance_id, 10) : null;

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
          target_difficulty: Number.isNaN(difficulty) ? 3 : difficulty,
          specialization_id: Number.isNaN(specializationId) ? null : specializationId,
          resonance_id: Number.isNaN(resonanceId) ? null : resonanceId,
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
  const errorMessage = patchMutation.isError ? extractErrorMessage(patchMutation.error) : null;

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
                  (pending proper picker — enter the Trait PK for now)
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
                  (pending proper picker — enter the Skill PK for now)
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

            {/* Resonance (optional FK id) — TODO Phase 10 */}
            <div>
              <label htmlFor="anima-ritual-resonance-id" className="mb-1 block text-sm font-medium">
                Resonance ID <span className="text-xs text-muted-foreground">(optional)</span>
              </label>
              <input
                id="anima-ritual-resonance-id"
                type="number"
                min={1}
                value={form.resonance_id}
                onChange={(e) => handleChange('resonance_id', e.target.value)}
                disabled={patchMutation.isPending}
                data-testid="field-resonance-id"
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
                  (pending proper picker — enter the CheckType PK for now)
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
                Target Difficulty
              </label>
              <input
                id="anima-ritual-target-difficulty"
                type="number"
                min={1}
                max={10}
                value={form.target_difficulty}
                onChange={(e) => handleChange('target_difficulty', e.target.value)}
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

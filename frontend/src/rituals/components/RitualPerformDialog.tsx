/**
 * RitualPerformDialog — Radix Dialog that wraps RitualForm, validates required
 * fields, submits to POST /api/magic/rituals/perform/, and surfaces typed errors.
 *
 * Shell pattern mirrors frontend/src/stories/components/AcceptOfferDialog.tsx.
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
import { RitualForm } from './RitualForm';
import { usePerformRitual } from '@/rituals/queries';
import type { RitualWithSchema, RitualInputSchema, PerformRitualResponse } from '../types';

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface RitualPerformDialogProps {
  ritual: RitualWithSchema;
  characterSheetId: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSuccess?: (response: PerformRitualResponse) => void;
}

// ---------------------------------------------------------------------------
// Error shape helpers
// ---------------------------------------------------------------------------

function extractErrorMessage(error: unknown): string {
  if (error instanceof Error && error.message) return error.message;
  return 'Failed to perform ritual';
}

// ---------------------------------------------------------------------------
// Required-field validation
// ---------------------------------------------------------------------------

function hasAllRequired(
  schema: RitualInputSchema | null,
  values: Record<string, string | number | null>
): boolean {
  if (!schema) return true;
  return schema.fields
    .filter((f) => f.required === true)
    .every((f) => {
      const v = values[f.name];
      if (v === null || v === undefined) return false;
      if (typeof v === 'string') return v.trim().length > 0;
      return true;
    });
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function RitualPerformDialog({
  ritual,
  characterSheetId,
  open,
  onOpenChange,
  onSuccess,
}: RitualPerformDialogProps) {
  const schema = ritual.input_schema as RitualInputSchema | null;

  const initialValues = (): Record<string, string | number | null> => {
    if (!schema) return {};
    return Object.fromEntries(schema.fields.map((f) => [f.name, null]));
  };

  const [values, setValues] = useState<Record<string, string | number | null>>(initialValues);

  const performMutation = usePerformRitual();

  function resetForm() {
    setValues(initialValues());
    performMutation.reset();
  }

  function handleOpenChange(next: boolean) {
    onOpenChange(next);
    if (!next) resetForm();
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();

    performMutation.mutate(
      {
        ritual_id: ritual.id,
        character_sheet_id: characterSheetId,
        kwargs: values as Record<string, string | number | boolean | null>,
      },
      {
        onSuccess: (response) => {
          handleOpenChange(false);
          onSuccess?.(response);
        },
      }
    );
  }

  const canSubmit = hasAllRequired(schema, values) && !performMutation.isPending;
  const errorMessage = performMutation.isError ? extractErrorMessage(performMutation.error) : null;

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>{ritual.name}</DialogTitle>
            <DialogDescription>{ritual.description}</DialogDescription>
          </DialogHeader>

          {/* Narrative prose block */}
          {ritual.narrative_prose && (
            <p
              data-testid="ritual-narrative-prose"
              className="mt-4 rounded-md bg-muted px-3 py-2 text-sm italic text-muted-foreground"
            >
              {ritual.narrative_prose}
            </p>
          )}

          {/* Error banner */}
          {errorMessage && (
            <div className="mt-4 rounded-md bg-destructive/10 px-4 py-3 text-sm text-destructive">
              <p>{errorMessage}</p>
            </div>
          )}

          {/* Dynamic form — only when schema is present */}
          {schema && (
            <div className="mt-4">
              <RitualForm
                schema={schema}
                values={values}
                onChange={setValues}
                disabled={performMutation.isPending}
                characterSheetId={characterSheetId}
              />
            </div>
          )}

          <DialogFooter className="mt-6">
            <Button
              type="button"
              variant="outline"
              onClick={() => handleOpenChange(false)}
              disabled={performMutation.isPending}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={!canSubmit} data-testid="ritual-perform-button">
              {performMutation.isPending ? 'Performing…' : 'Perform'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

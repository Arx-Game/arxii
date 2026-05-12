/**
 * RitualSessionResponseDialog — invitee accepts (with participant_fields form) or declines.
 *
 * Props:
 *   session        — full RitualSessionDetail (from useRitualSessionDetail)
 *   participantId  — the current user's character sheet id (used to look up their participant row)
 *   open           — dialog open state
 *   onOpenChange   — close handler
 *   onSuccess      — called after accept or decline succeeds
 *
 * The ritual's participant_fields schema is NOT in RitualSessionDetail — it lives in the
 * ritual's input_schema.participant_fields. Since we don't always have the full ritual
 * here, participant_fields schema is passed as an optional prop. If absent, only the
 * Decline button and a plain Accept button (no form) are shown.
 *
 * --- depends_on path resolution ---
 * CovenantRolePickerField has `depends_on: "session.target_covenant.covenant_type"`.
 * RitualSessionDetail.session_kwargs contains `target_covenant` as a covenant PK (number).
 * We resolve this path by:
 *   1. Extracting target_covenant_id from session_kwargs (cast to unknown→Record).
 *   2. Fetching GET /api/covenants/covenants/{id}/ to get covenant_type.
 *   3. Injecting the resolved value into formValues under the full depends_on key
 *      "session.target_covenant.covenant_type" before passing to RitualForm.
 * CovenantRolePickerField reads formValues[field.depends_on] — the key is the full path
 * string, so no changes are needed to CovenantRolePickerField itself.
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
import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '@/evennia_replacements/api';
import { RitualForm } from './RitualForm';
import { useAcceptRitualSession, useDeclineRitualSession } from '@/rituals/queries';
import type { RitualSessionDetail } from '../api';
import type { RitualInputSchema } from '../types';
import type { components } from '@/generated/api';

type Covenant = components['schemas']['Covenant'];

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface RitualSessionResponseDialogProps {
  session: RitualSessionDetail;
  participantId: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Optional participant_fields schema — when provided, Accept shows the form. */
  participantFieldsSchema?: RitualInputSchema | null;
  onSuccess?: () => void;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function extractErrorMessage(error: unknown): string {
  if (error instanceof Error && error.message) return error.message;
  return 'Operation failed';
}

/**
 * Extract the target_covenant id from session_kwargs.
 * session_kwargs is typed as `unknown` in the generated schema.
 * We defensively cast and look for a `target_covenant` number field.
 */
function extractTargetCovenantId(sessionKwargs: unknown): number | null {
  if (typeof sessionKwargs !== 'object' || sessionKwargs === null) return null;
  const kw = sessionKwargs as Record<string, unknown>;
  const v = kw['target_covenant'];
  if (typeof v === 'number') return v;
  if (typeof v === 'string') {
    const n = Number(v);
    return isNaN(n) ? null : n;
  }
  return null;
}

// ---------------------------------------------------------------------------
// Hook: resolve target_covenant → covenant_type
// ---------------------------------------------------------------------------

async function fetchCovenant(id: number): Promise<Covenant> {
  const res = await apiFetch(`/api/covenants/covenants/${id}/`);
  if (!res.ok) throw new Error(`Failed to load covenant ${id}`);
  return res.json() as Promise<Covenant>;
}

function useTargetCovenantType(sessionKwargs: unknown): string | null {
  const covenantId = extractTargetCovenantId(sessionKwargs);

  const { data } = useQuery({
    queryKey: ['covenants', 'detail', covenantId],
    queryFn: () => fetchCovenant(covenantId!),
    enabled: covenantId != null,
    staleTime: 60_000,
  });

  return data?.covenant_type ?? null;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function RitualSessionResponseDialog({
  session,
  participantId,
  open,
  onOpenChange,
  participantFieldsSchema,
  onSuccess,
}: RitualSessionResponseDialogProps) {
  const [participantValues, setParticipantValues] = useState<
    Record<string, string | number | null>
  >(() => {
    if (!participantFieldsSchema) return {};
    return Object.fromEntries(participantFieldsSchema.fields.map((f) => [f.name, null]));
  });

  const acceptMutation = useAcceptRitualSession();
  const declineMutation = useDeclineRitualSession();

  // Resolve depends_on path "session.target_covenant.covenant_type".
  // We fetch the target covenant's type and inject it into formValues under the full
  // depends_on key. CovenantRolePickerField reads formValues[field.depends_on] which
  // is the full string "session.target_covenant.covenant_type" — so the key must match.
  const targetCovenantType = useTargetCovenantType(session.session_kwargs);

  /**
   * Build the formValues passed to RitualForm, injecting the resolved covenant_type
   * under the full depends_on path key so CovenantRolePickerField can read it.
   */
  const formValuesWithResolved: Record<string, string | number | null> = {
    ...participantValues,
    // Inject resolved path value so CovenantRolePickerField finds it via:
    //   formValues[field.depends_on]  where depends_on = "session.target_covenant.covenant_type"
    'session.target_covenant.covenant_type': targetCovenantType,
  };

  function resetForm() {
    setParticipantValues(
      participantFieldsSchema
        ? Object.fromEntries(participantFieldsSchema.fields.map((f) => [f.name, null]))
        : {}
    );
    acceptMutation.reset();
    declineMutation.reset();
  }

  function handleOpenChange(next: boolean) {
    onOpenChange(next);
    if (!next) resetForm();
  }

  function handleDecline() {
    declineMutation.mutate(session.id, {
      onSuccess: () => {
        handleOpenChange(false);
        onSuccess?.();
      },
    });
  }

  function handleAccept() {
    // Build participant_kwargs from form values; filter out null values
    const participant_kwargs: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(participantValues)) {
      if (v !== null && v !== undefined) {
        participant_kwargs[k] = v;
      }
    }

    acceptMutation.mutate(
      {
        id: session.id,
        body: {
          participant_kwargs:
            Object.keys(participant_kwargs).length > 0 ? participant_kwargs : undefined,
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

  const hasSchema = participantFieldsSchema && participantFieldsSchema.fields.length > 0;

  // Required-field validation: all required participant_fields must have a value
  const canAccept = !hasSchema
    ? true
    : participantFieldsSchema.fields
        .filter((f) => f.required === true)
        .every((f) => {
          const v = participantValues[f.name];
          if (v === null || v === undefined) return false;
          if (typeof v === 'string') return v.trim().length > 0;
          return true;
        });

  const isPending = acceptMutation.isPending || declineMutation.isPending;

  const errorMessage = acceptMutation.isError
    ? extractErrorMessage(acceptMutation.error)
    : declineMutation.isError
      ? extractErrorMessage(declineMutation.error)
      : null;

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Respond to Invitation</DialogTitle>
          <DialogDescription>
            {session.ritual_name} — from {session.initiator_name}
          </DialogDescription>
        </DialogHeader>

        {/* Proposed terms */}
        {session.proposed_terms && (
          <p className="mt-4 rounded-md bg-muted px-3 py-2 text-sm italic text-muted-foreground">
            {session.proposed_terms}
          </p>
        )}

        {/* Error banner */}
        {errorMessage && (
          <div className="mt-4 rounded-md bg-destructive/10 px-4 py-3 text-sm text-destructive">
            <p>{errorMessage}</p>
          </div>
        )}

        {/* Participant fields form (shown before accepting) */}
        {hasSchema && (
          <div className="mt-4">
            <p className="mb-2 text-sm font-medium text-foreground">
              Your choices (required to accept):
            </p>
            <RitualForm
              schema={participantFieldsSchema}
              values={formValuesWithResolved}
              onChange={setParticipantValues}
              disabled={isPending}
            />
          </div>
        )}

        <DialogFooter className="mt-6 flex gap-2">
          <Button
            type="button"
            variant="outline"
            onClick={() => handleOpenChange(false)}
            disabled={isPending}
          >
            Close
          </Button>
          <Button
            type="button"
            variant="destructive"
            onClick={handleDecline}
            disabled={isPending}
            data-testid="decline-button"
          >
            {declineMutation.isPending ? 'Declining…' : 'Decline'}
          </Button>
          <Button
            type="button"
            onClick={handleAccept}
            disabled={!canAccept || isPending}
            data-testid="accept-button"
          >
            {acceptMutation.isPending ? 'Accepting…' : 'Accept'}
          </Button>
        </DialogFooter>

        {/* Note about participantId (used externally for display; no-op here) */}
        <input type="hidden" value={participantId} />
      </DialogContent>
    </Dialog>
  );
}

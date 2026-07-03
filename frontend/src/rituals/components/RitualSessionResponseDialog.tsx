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
 * Two strategies, tried together:
 *
 *  1. Session-reference path (induction): CovenantRolePickerField declares
 *     `depends_on: "session.target_covenant.covenant_type"`. We resolve this by:
 *     a. Reading the COVENANT-kind entry from session.session_references (falls
 *        back to extracting target_covenant from session_kwargs for older sessions).
 *     b. Fetching GET /api/covenants/covenants/{id}/ to get covenant_type.
 *     c. Injecting the resolved value into formValues under the full depends_on key.
 *
 *  2. Bare session-kwargs key (formation): CovenantRolePickerField declares
 *     `depends_on: "covenant_type"`. We inject all string/number session_kwargs
 *     under their bare keys, so the picker finds the value directly — no fetch.
 *
 * CovenantRolePickerField reads formValues[field.depends_on]; the key matches the
 * depends_on string, so no changes are needed to CovenantRolePickerField itself.
 *
 * --- applies_to gating ---
 * Fields with applies_to === "candidate_only" are hidden from the initiator. The
 * effectiveSchema reflects only the fields the viewer should fill in.
 *
 * --- emits_reference ---
 * On accept, fields with emits_reference are sent as typed references entries (not
 * participant_kwargs). COVENANT_ROLE → ref_covenant_role_id; COVENANT → ref_covenant_id.
 */

import { useMemo, useState } from 'react';
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
import { extractErrorMessage } from '@/lib/errors';
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

/**
 * Resolve target_covenant id from the session-level COVENANT reference.
 * session_references is typed as `string` in the generated schema (SerializerMethodField),
 * but at runtime it's an array of reference objects.
 */
function targetCovenantIdFromRefs(session: RitualSessionDetail): number | null {
  const raw = session.session_references as unknown;
  if (!Array.isArray(raw)) return null;
  const refs = raw as Array<{ kind: string; ref_covenant_id?: number }>;
  const covRef = refs.find((r) => r.kind === 'COVENANT' && r.ref_covenant_id != null);
  return covRef?.ref_covenant_id ?? null;
}

/**
 * Extract the target_covenant id from session_kwargs (legacy fallback).
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

function useTargetCovenantType(session: RitualSessionDetail): string | null {
  // Prefer the session-level COVENANT reference; fall back to session_kwargs for older sessions.
  const covenantId =
    targetCovenantIdFromRefs(session) ?? extractTargetCovenantId(session.session_kwargs);

  const { data } = useQuery({
    queryKey: ['covenants', 'detail', covenantId],
    queryFn: () => fetchCovenant(covenantId!),
    enabled: covenantId != null,
    staleTime: 60_000,
  });

  return data?.covenant_type ?? null;
}

/**
 * Extract session_kwargs as a flat record suitable for depends_on resolution.
 *
 * FORMATION's chosen_covenant_role field uses depends_on: "covenant_type" — a
 * bare key into session_kwargs. By injecting all session kwargs under their
 * bare keys, CovenantRolePickerField finds the value via formValues[field.depends_on].
 *
 * Only string and number values are injected; nested objects/arrays are skipped
 * (no current depends_on key references them).
 */
function extractSessionKwargsForDependsOn(sessionKwargs: unknown): Record<string, string | number> {
  const result: Record<string, string | number> = {};
  if (typeof sessionKwargs !== 'object' || sessionKwargs === null) return result;
  const kw = sessionKwargs as Record<string, unknown>;
  for (const [k, v] of Object.entries(kw)) {
    if (typeof v === 'string' || typeof v === 'number') {
      result[k] = v;
    }
  }
  return result;
}

// ---------------------------------------------------------------------------
// Module-level constants
// ---------------------------------------------------------------------------

/** Maps emits_reference kind to the correct id key for the reference object. */
const REF_ID_KEY: Record<string, 'ref_covenant_id' | 'ref_covenant_role_id'> = {
  COVENANT: 'ref_covenant_id',
  COVENANT_ROLE: 'ref_covenant_role_id',
};

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
  // Gate fields by applies_to: the initiator does not see candidate_only fields.
  // Hoisted above useState so the initial seed uses the same filtered field set.
  const isInitiator = participantId === session.initiator_id;
  const effectiveSchema = useMemo(() => {
    if (!participantFieldsSchema) return participantFieldsSchema;
    const visibleFields = participantFieldsSchema.fields.filter(
      (f) => !(f.applies_to === 'candidate_only' && isInitiator)
    );
    return { ...participantFieldsSchema, fields: visibleFields };
  }, [participantFieldsSchema, isInitiator]);

  const [participantValues, setParticipantValues] = useState<
    Record<string, string | number | null>
  >(() => {
    if (!effectiveSchema) return {};
    return Object.fromEntries(effectiveSchema.fields.map((f) => [f.name, null]));
  });

  const acceptMutation = useAcceptRitualSession();
  const declineMutation = useDeclineRitualSession();

  // Resolve depends_on paths.
  //
  // Two resolution strategies, tried in order:
  //  1. Session-reference path (induction): "session.target_covenant.covenant_type"
  //     — fetch the COVENANT referenced at session level and read its covenant_type.
  //  2. Bare session-kwargs key (formation): "covenant_type"
  //     — read the value directly from session.session_kwargs.
  //
  // CovenantRolePickerField reads formValues[field.depends_on]; we inject the
  // resolved value under that key so the picker can find it.
  const targetCovenantType = useTargetCovenantType(session);

  /**
   * Build the formValues passed to RitualForm, injecting resolved depends_on
   * values so dependent fields (e.g. CovenantRolePickerField) can read them.
   */
  const formValuesWithResolved: Record<string, string | number | null> = {
    ...participantValues,
    // Session-kwargs values: inject every session kwarg under its bare key so
    // fields with depends_on pointing at a session kwarg (e.g. "covenant_type"
    // in FORMATION) resolve without a separate fetch.
    ...extractSessionKwargsForDependsOn(session.session_kwargs),
    // Session-reference path (induction): the resolved covenant_type from the
    // COVENANT session-reference, injected under the full path key.
    'session.target_covenant.covenant_type': targetCovenantType,
  };

  function resetForm() {
    setParticipantValues(
      effectiveSchema ? Object.fromEntries(effectiveSchema.fields.map((f) => [f.name, null])) : {}
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
    // Split form values: fields with emits_reference become references entries;
    // remaining non-null values go into participant_kwargs.
    const participant_kwargs: Record<string, unknown> = {};
    const references: Array<Record<string, unknown>> = [];
    const fieldByName = new Map((effectiveSchema?.fields ?? []).map((f) => [f.name, f]));
    for (const [k, v] of Object.entries(participantValues)) {
      if (v === null || v === undefined) continue;
      const emits = fieldByName.get(k)?.emits_reference;
      if (emits) {
        const idKey = REF_ID_KEY[emits];
        if (idKey) references.push({ kind: emits, [idKey]: v });
      } else {
        participant_kwargs[k] = v;
      }
    }

    acceptMutation.mutate(
      {
        id: session.id,
        body: {
          participant_kwargs:
            Object.keys(participant_kwargs).length > 0 ? participant_kwargs : undefined,
          references: references.length > 0 ? references : undefined,
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

  const hasSchema = effectiveSchema && effectiveSchema.fields.length > 0;

  // Required-field validation: all required participant_fields must have a value
  const canAccept = !hasSchema
    ? true
    : effectiveSchema.fields
        .filter((f) => f.required === true)
        .every((f) => {
          const v = participantValues[f.name];
          if (v === null || v === undefined) return false;
          if (typeof v === 'string') return v.trim().length > 0;
          return true;
        });

  const isPending = acceptMutation.isPending || declineMutation.isPending;

  const errorMessage = acceptMutation.isError
    ? extractErrorMessage(acceptMutation.error, 'Operation failed')
    : declineMutation.isError
      ? extractErrorMessage(declineMutation.error, 'Operation failed')
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
              schema={effectiveSchema}
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

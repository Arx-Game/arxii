/**
 * RitualSessionDraftDialog — initiator drafts a new ritual session.
 *
 * Renders the ritual's session-level `fields` array (from input_schema) plus
 * an invitee picker (multi-select via InviteePickerField — a local multi-character
 * search built inline because CharacterSearchField only supports single selection).
 *
 * Submits via useDraftRitualSession(). On success, closes and calls onSuccess
 * with the session id so the caller can navigate to the detail page.
 */

import { useState, useEffect, useRef } from 'react';
import type React from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { RitualForm } from './RitualForm';
import { useDraftRitualSession } from '@/rituals/queries';
import { searchPersonas } from '@/events/queries';
import type { RitualWithSchema, RitualInputSchema } from '../types';
import type { RitualSessionDraft } from '../api';

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface RitualSessionDraftDialogProps {
  ritual: RitualWithSchema;
  /** The initiator's character sheet id. The backend infers the initiator from the
   *  authenticated session — this is kept for caller symmetry with RitualPerformDialog. */
  characterSheetId: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSuccess?: (session: RitualSessionDraft) => void;
}

// ---------------------------------------------------------------------------
// Multi-character invitee picker
// ---------------------------------------------------------------------------

interface PersonaOption {
  id: number;
  name: string;
}

interface InviteePickerProps {
  selected: PersonaOption[];
  onAdd: (persona: PersonaOption) => void;
  onRemove: (id: number) => void;
  disabled?: boolean;
}

function InviteePicker({ selected, onAdd, onRemove, disabled }: InviteePickerProps) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<PersonaOption[]>([]);
  const [searching, setSearching] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (query.trim().length < 2) {
      setResults([]);
      return;
    }
    debounceRef.current = setTimeout(() => {
      setSearching(true);
      searchPersonas(query.trim())
        .then((res) => {
          // Filter out already-selected personas
          const selectedIds = new Set(selected.map((p) => p.id));
          setResults(res.filter((r) => !selectedIds.has(r.id)));
        })
        .catch(() => setResults([]))
        .finally(() => setSearching(false));
    }, 300);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [query, selected]);

  function handleSelect(persona: PersonaOption) {
    onAdd(persona);
    setQuery('');
    setResults([]);
  }

  function handleInputChange(e: React.ChangeEvent<HTMLInputElement>) {
    setQuery(e.target.value);
  }

  return (
    <div className="space-y-2">
      <Label>Invitees</Label>

      {/* Selected chips */}
      {selected.length > 0 && (
        <div className="flex flex-wrap gap-1" data-testid="invitee-chips">
          {selected.map((p) => (
            <span
              key={p.id}
              className="flex items-center gap-1 rounded-full bg-accent px-2 py-0.5 text-xs"
            >
              {p.name}
              <button
                type="button"
                onClick={() => onRemove(p.id)}
                disabled={disabled}
                className="ml-0.5 text-muted-foreground hover:text-foreground"
                aria-label={`Remove ${p.name}`}
              >
                ×
              </button>
            </span>
          ))}
        </div>
      )}

      {/* Search input */}
      <div className="relative">
        <Input
          value={query}
          onChange={handleInputChange}
          placeholder="Search for a character to invite…"
          autoComplete="off"
          disabled={disabled}
          data-testid="invitee-search-input"
        />
        {searching && (
          <span className="absolute right-2 top-2 text-xs text-muted-foreground">Searching…</span>
        )}
        {results.length > 0 && (
          <ul className="absolute z-50 mt-1 max-h-48 w-full overflow-auto rounded-md border bg-popover shadow-lg">
            {results.map((p) => (
              <li key={p.id}>
                <button
                  type="button"
                  className="w-full px-3 py-2 text-left text-sm hover:bg-accent"
                  onClick={() => handleSelect(p)}
                >
                  {p.name}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Required-field validation (mirrors RitualPerformDialog)
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

function extractErrorMessage(error: unknown): string {
  if (error instanceof Error && error.message) return error.message;
  return 'Failed to draft ritual session';
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function RitualSessionDraftDialog({
  ritual,
  characterSheetId: _characterSheetId,
  open,
  onOpenChange,
  onSuccess,
}: RitualSessionDraftDialogProps) {
  const schema = ritual.input_schema as RitualInputSchema | null;

  const initialValues = (): Record<string, string | number | null> => {
    if (!schema) return {};
    return Object.fromEntries(schema.fields.map((f) => [f.name, null]));
  };

  const [values, setValues] = useState<Record<string, string | number | null>>(initialValues);
  const [invitees, setInvitees] = useState<Array<{ id: number; name: string }>>([]);
  const [proposedTerms, setProposedTerms] = useState('');

  const draftMutation = useDraftRitualSession();

  function resetForm() {
    setValues(initialValues());
    setInvitees([]);
    setProposedTerms('');
    draftMutation.reset();
  }

  function handleOpenChange(next: boolean) {
    onOpenChange(next);
    if (!next) resetForm();
  }

  function handleAddInvitee(persona: { id: number; name: string }) {
    setInvitees((prev) => {
      if (prev.some((p) => p.id === persona.id)) return prev;
      return [...prev, persona];
    });
  }

  function handleRemoveInvitee(id: number) {
    setInvitees((prev) => prev.filter((p) => p.id !== id));
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();

    // Build session_kwargs from schema field values
    const session_kwargs: Record<string, unknown> = {};
    if (schema) {
      for (const f of schema.fields) {
        const v = values[f.name];
        if (v !== null && v !== undefined) {
          session_kwargs[f.name] = v;
        }
      }
    }

    draftMutation.mutate(
      {
        ritual_id: ritual.id,
        proposed_terms: proposedTerms,
        invitee_ids: invitees.map((p) => p.id),
        session_kwargs: Object.keys(session_kwargs).length > 0 ? session_kwargs : undefined,
      },
      {
        onSuccess: (session) => {
          handleOpenChange(false);
          onSuccess?.(session);
        },
      }
    );
  }

  const canSubmit =
    hasAllRequired(schema, values) &&
    !draftMutation.isPending &&
    // At least one invitee required to form a session
    invitees.length > 0;

  const errorMessage = draftMutation.isError ? extractErrorMessage(draftMutation.error) : null;
  const isPending = draftMutation.isPending;

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>{ritual.name}</DialogTitle>
            <DialogDescription>
              Draft a session invitation. Invitees can accept or decline.
            </DialogDescription>
          </DialogHeader>

          {/* Narrative prose */}
          {ritual.narrative_prose && (
            <p className="mt-4 rounded-md bg-muted px-3 py-2 text-sm italic text-muted-foreground">
              {ritual.narrative_prose}
            </p>
          )}

          {/* Error banner */}
          {errorMessage && (
            <div className="mt-4 rounded-md bg-destructive/10 px-4 py-3 text-sm text-destructive">
              <p>{errorMessage}</p>
            </div>
          )}

          <div className="mt-4 space-y-4">
            {/* Proposed terms */}
            <div className="space-y-2">
              <Label htmlFor="proposed-terms">Proposed terms</Label>
              <Input
                id="proposed-terms"
                value={proposedTerms}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                  setProposedTerms(e.target.value)
                }
                placeholder="Optional notes for invitees…"
                disabled={isPending}
                data-testid="proposed-terms-input"
              />
            </div>

            {/* Invitees */}
            <InviteePicker
              selected={invitees}
              onAdd={handleAddInvitee}
              onRemove={handleRemoveInvitee}
              disabled={isPending}
            />

            {/* Dynamic session-level fields (if any) */}
            {schema && schema.fields.length > 0 && (
              <RitualForm
                schema={schema}
                values={values}
                onChange={setValues}
                disabled={isPending}
              />
            )}
          </div>

          <DialogFooter className="mt-6">
            <Button
              type="button"
              variant="outline"
              onClick={() => handleOpenChange(false)}
              disabled={isPending}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={!canSubmit} data-testid="draft-submit-button">
              {isPending ? 'Sending…' : 'Send Invitations'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

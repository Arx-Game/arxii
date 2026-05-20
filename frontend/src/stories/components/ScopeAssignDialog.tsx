/**
 * ScopeAssignDialog — Task E4
 *
 * Lifts an UNASSIGNED story into a runnable scope from the author page.
 * Scope choices are exactly character / group / global (UNASSIGNED is not an
 * assignable input — the server rejects it; covenant is not supported by the
 * assign path).
 *
 * The combo invariant is enforced server-side (B2 + the re-assign Critical
 * fix); this dialog mirrors it client-side so the submit button stays
 * disabled until a valid combination is selected:
 *   - character → requires character_sheet (forbids gm_table)
 *   - group     → requires gm_table        (forbids character_sheet)
 *   - global    → forbids both
 *
 * Pickers (minimal-functional):
 *   - GM table: reuses the existing `useTables()` hook (`@/tables/queries`)
 *     rendered as a native <select>. A clean reusable hook exists, so we use
 *     it rather than a raw id input.
 *   - CharacterSheet: there is no reusable CharacterSheet picker/search
 *     component in the frontend (only a display page), so per the plan a
 *     typed numeric-id <Input> with a clear label is used.
 *
 * DRF-400 surfacing mirrors PromoteMaturityButton exactly: the apiFetch error
 * carries the failed `Response`; `response.json()` resolves to the DRF body,
 * from which we read the `scope` field error / `non_field_errors` / `detail`
 * and render it INLINE (the "already assigned" 400 lands under `scope`).
 *
 * Success relies on the hook's query invalidation (useAssignStory invalidates
 * story / list / myActive / gmQueue); no manual refetch.
 */

import { useState } from 'react';
import { toast } from 'sonner';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { useTables } from '@/tables/queries';
import { useAssignStory } from '../queries';
import type { AssignableStoryScope, AssignStoryBody } from '../types';

// ---------------------------------------------------------------------------
// DRF error shape — the assign action 400s with { scope: "<message>" } for
// the "already assigned" precondition. The manual scope/target-invariant
// errors emit BARE strings under character_sheet/gm_table, while DRF
// invalid-PK list errors arrive as string[]; standard combo errors arrive
// under non_field_errors / detail. Every keyed field may therefore be a
// string OR a string[] (handled by `pick` below).
// ---------------------------------------------------------------------------

interface AssignDRFError {
  scope?: string | string[];
  character_sheet?: string | string[];
  gm_table?: string | string[];
  non_field_errors?: string | string[];
  detail?: string;
}

// ---------------------------------------------------------------------------
// Scope options — exactly character / group / global.
// ---------------------------------------------------------------------------

const SCOPE_OPTIONS: { value: AssignableStoryScope; label: string }[] = [
  { value: 'character', label: "Character — one person's personal story" },
  { value: 'group', label: "Group — a table's shared story" },
  { value: 'global', label: 'Global — affects the whole metaplot' },
];

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface ScopeAssignDialogProps {
  storyId: number;
  /** Optional controlled-open wiring (consistent with other dialogs). */
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function ScopeAssignDialog({ storyId, open, onOpenChange }: ScopeAssignDialogProps) {
  const isControlled = open !== undefined;
  const [internalOpen, setInternalOpen] = useState(false);
  const dialogOpen = isControlled ? open : internalOpen;

  const [scope, setScope] = useState<AssignableStoryScope>('character');
  const [characterSheetId, setCharacterSheetId] = useState('');
  const [gmTableId, setGmTableId] = useState('');
  const [inlineError, setInlineError] = useState('');

  const assignMutation = useAssignStory();
  const tablesQuery = useTables({ page_size: 100 });
  const tables = tablesQuery.data?.results ?? [];

  function setOpen(next: boolean) {
    if (isControlled) {
      onOpenChange?.(next);
    } else {
      setInternalOpen(next);
    }
  }

  function resetForm() {
    setScope('character');
    setCharacterSheetId('');
    setGmTableId('');
    setInlineError('');
  }

  function handleOpenChange(next: boolean) {
    if (!next) resetForm();
    setOpen(next);
  }

  // Client-side mirror of the server combo invariant.
  const characterSheetValue = Number.parseInt(characterSheetId, 10);
  const gmTableValue = Number.parseInt(gmTableId, 10);
  const hasCharacterSheet = Number.isInteger(characterSheetValue) && characterSheetValue > 0;
  const hasGmTable = Number.isInteger(gmTableValue) && gmTableValue > 0;

  const isValid =
    scope === 'global' ||
    (scope === 'character' && hasCharacterSheet) ||
    (scope === 'group' && hasGmTable);

  function handleError(err: unknown) {
    if (err && typeof err === 'object' && 'response' in err) {
      const response = (err as { response?: Response }).response;
      if (response) {
        void response
          .json()
          .then((data: unknown) => {
            if (data && typeof data === 'object') {
              const body = data as AssignDRFError;
              // Each keyed field may be a bare string (manual invariant
              // errors) or a string[] (DRF list errors) — guard before join.
              const pick = (v: string | string[] | undefined): string | undefined =>
                Array.isArray(v) ? v.join(' ') : v;
              const message =
                pick(body.scope) ||
                pick(body.character_sheet) ||
                pick(body.gm_table) ||
                pick(body.non_field_errors) ||
                body.detail ||
                'Assignment failed. Please try again.';
              setInlineError(message);
            } else {
              setInlineError('Assignment failed. Please try again.');
            }
          })
          .catch(() => setInlineError('Assignment failed. Please try again.'));
        return;
      }
    }
    setInlineError(err instanceof Error ? err.message : 'Assignment failed. Please try again.');
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!isValid) return;
    setInlineError('');

    // Carry ONLY the scope-appropriate target.
    const body: AssignStoryBody = { scope };
    if (scope === 'character') {
      body.character_sheet = characterSheetValue;
    } else if (scope === 'group') {
      body.gm_table = gmTableValue;
    }

    assignMutation.mutate(
      { storyId, ...body },
      {
        onSuccess: () => {
          setInlineError('');
          toast.success('Story assigned to scope');
          handleOpenChange(false);
        },
        onError: handleError,
      }
    );
  }

  return (
    <Dialog open={dialogOpen} onOpenChange={handleOpenChange}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm" data-testid="assign-scope-btn">
          Assign scope
        </Button>
      </DialogTrigger>

      <DialogContent className="sm:max-w-lg">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>Assign Story to a Scope</DialogTitle>
            <DialogDescription>
              Lift this story out of Unassigned into a runnable scope. This cannot be changed
              afterwards.
            </DialogDescription>
          </DialogHeader>

          {inlineError && (
            <div
              data-testid="scope-assign-error"
              className="mt-4 rounded-md bg-destructive/10 px-4 py-3 text-sm text-destructive"
            >
              {inlineError}
            </div>
          )}

          <div className="mt-4 grid gap-4">
            {/* Scope */}
            <div className="space-y-2">
              <Label>Scope</Label>
              <RadioGroup
                value={scope}
                onValueChange={(val) => {
                  setScope(val as AssignableStoryScope);
                  setInlineError('');
                }}
                className="flex flex-col gap-2"
                data-testid="scope-assign-scope-group"
              >
                {SCOPE_OPTIONS.map(({ value, label }) => (
                  <label
                    key={value}
                    className="flex cursor-pointer items-center gap-3 rounded-md border p-3 hover:bg-accent"
                  >
                    <RadioGroupItem value={value} id={`scope-assign-${value}`} />
                    <span className="text-sm">{label}</span>
                  </label>
                ))}
              </RadioGroup>
            </div>

            {/* Conditional target — character */}
            {scope === 'character' && (
              <div className="space-y-1.5">
                <Label htmlFor="scope-assign-character-sheet">
                  Character Sheet ID <span className="text-destructive">*</span>
                </Label>
                <Input
                  id="scope-assign-character-sheet"
                  type="number"
                  min="1"
                  inputMode="numeric"
                  value={characterSheetId}
                  onChange={(e) => setCharacterSheetId(e.target.value)}
                  placeholder="e.g. 42"
                />
                <p className="text-xs text-muted-foreground">
                  The owning character&apos;s sheet ID for this personal story.
                </p>
              </div>
            )}

            {/* Conditional target — group (GM table) */}
            {scope === 'group' && (
              <div className="space-y-1.5">
                <Label htmlFor="scope-assign-gm-table">
                  GM Table <span className="text-destructive">*</span>
                </Label>
                <select
                  id="scope-assign-gm-table"
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                  value={gmTableId}
                  onChange={(e) => setGmTableId(e.target.value)}
                >
                  <option value="">Select a GM table…</option>
                  {tables.map((table) => (
                    <option key={table.id} value={table.id}>
                      {table.name}
                    </option>
                  ))}
                </select>
                <p className="text-xs text-muted-foreground">
                  The GM table that will run this group story.
                </p>
              </div>
            )}

            {/* global: no target input */}
            {scope === 'global' && (
              <p className="text-sm text-muted-foreground">
                Global stories have no owning character or table.
              </p>
            )}
          </div>

          <DialogFooter className="mt-6">
            <Button
              type="button"
              variant="outline"
              onClick={() => handleOpenChange(false)}
              disabled={assignMutation.isPending}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={!isValid || assignMutation.isPending}>
              {assignMutation.isPending ? 'Assigning…' : 'Assign'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

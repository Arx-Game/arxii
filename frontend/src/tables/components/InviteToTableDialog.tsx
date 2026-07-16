/**
 * InviteToTableDialog — GM invites a persona to the table.
 *
 * Persona selection uses a debounced text search against /api/personas/?search=
 * — the same pattern established in ScheduleEventDialog.
 */

import { useState } from 'react';
import { toast } from 'sonner';
import { bulletinErrorsFrom, type BulletinFieldErrors } from '../bulletinErrors';
import { FieldError, FormErrors } from './FieldError';
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
import { usePersonaSearch } from '@/roster/usePersonaSearch';
import { useInviteToTable } from '../queries';
import type { GMTable } from '../types';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface PersonaOption {
  id: number;
  name: string;
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface InviteToTableDialogProps {
  table: GMTable;
  children: React.ReactNode;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function InviteToTableDialog({ table, children }: InviteToTableDialogProps) {
  const [open, setOpen] = useState(false);
  const [personaQuery, setPersonaQuery] = useState('');
  const [selectedPersona, setSelectedPersona] = useState<PersonaOption | null>(null);
  const [fieldErrors, setFieldErrors] = useState<BulletinFieldErrors>({});

  const inviteMutation = useInviteToTable();

  // Debounced, race-safe persona search (2026-07 audit — shared hook).
  const { results, isFetching: personaSearching } = usePersonaSearch(personaQuery);
  // Suppress the dropdown once a persona is committed (query === its name).
  const personaResults = selectedPersona?.name === personaQuery ? [] : results;

  function resetForm() {
    setPersonaQuery('');
    setSelectedPersona(null);
    setFieldErrors({});
  }

  function handleOpenChange(next: boolean) {
    setOpen(next);
    if (!next) resetForm();
  }

  function handleSelectPersona(persona: PersonaOption) {
    setSelectedPersona(persona);
    setPersonaQuery(persona.name);
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedPersona) return;
    setFieldErrors({});

    inviteMutation.mutate(
      { table: table.id, persona: selectedPersona.id },
      {
        onSuccess: () => {
          toast.success(`${selectedPersona.name} invited to ${table.name}`);
          setOpen(false);
        },
        onError: (err: unknown) => {
          setFieldErrors(bulletinErrorsFrom(err));
        },
      }
    );
  }

  const isValid = selectedPersona !== null;

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger asChild>{children}</DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Invite to Table</DialogTitle>
          <DialogDescription>
            Search for a persona to invite to <strong>{table.name}</strong>.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={(e) => handleSubmit(e)} className="space-y-4">
          {/* Persona search */}
          <div className="space-y-1">
            <Label htmlFor="invite-persona">Persona *</Label>
            <div className="relative">
              <Input
                id="invite-persona"
                value={personaQuery}
                onChange={(e) => {
                  setPersonaQuery(e.target.value);
                  setSelectedPersona(null);
                }}
                placeholder="Search for a persona…"
                autoComplete="off"
              />
              {personaSearching && (
                <span className="absolute right-2 top-2 text-xs text-muted-foreground">
                  Searching…
                </span>
              )}
              {personaResults.length > 0 && (
                <ul className="absolute z-50 mt-1 max-h-48 w-full overflow-auto rounded-md border bg-popover shadow-lg">
                  {personaResults.map((p) => (
                    <li key={p.id}>
                      <button
                        type="button"
                        className="w-full px-3 py-2 text-left text-sm hover:bg-accent"
                        onClick={() => handleSelectPersona(p)}
                      >
                        {p.name}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <FieldError errors={fieldErrors} field="persona" />
          </div>

          {/* Global errors */}
          <FormErrors errors={fieldErrors} />

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={!isValid || inviteMutation.isPending}>
              {inviteMutation.isPending ? 'Inviting…' : 'Invite'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

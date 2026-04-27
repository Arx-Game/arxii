/**
 * InviteToTableDialog — GM invites a persona to the table.
 *
 * Persona selection uses a debounced text search against /api/personas/?search=
 * — the same pattern established in ScheduleEventDialog.
 */

import { useState, useEffect, useRef } from 'react';
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
import { searchPersonas } from '@/events/queries';
import { useInviteToTable } from '../queries';
import type { GMTable } from '../types';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface PersonaOption {
  id: number;
  name: string;
}

interface DRFFieldErrors {
  table?: string[];
  persona?: string[];
  non_field_errors?: string[];
  detail?: string;
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
  const [personaResults, setPersonaResults] = useState<PersonaOption[]>([]);
  const [selectedPersona, setSelectedPersona] = useState<PersonaOption | null>(null);
  const [personaSearching, setPersonaSearching] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<DRFFieldErrors>({});
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const inviteMutation = useInviteToTable();

  // Debounced persona search
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (personaQuery.trim().length < 2) {
      setPersonaResults([]);
      return;
    }
    debounceRef.current = setTimeout(() => {
      setPersonaSearching(true);
      searchPersonas(personaQuery.trim())
        .then((results) => setPersonaResults(results))
        .catch(() => setPersonaResults([]))
        .finally(() => setPersonaSearching(false));
    }, 300);
  }, [personaQuery]);

  function resetForm() {
    setPersonaQuery('');
    setPersonaResults([]);
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
    setPersonaResults([]);
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
        onError: async (err: unknown) => {
          const res = (err as { response?: Response })?.response;
          if (res) {
            const body = (await res.json()) as DRFFieldErrors;
            setFieldErrors(body);
          } else {
            toast.error('Failed to invite persona');
          }
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

        <form onSubmit={(e) => void handleSubmit(e)} className="space-y-4">
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
            {fieldErrors.persona && (
              <p className="text-sm text-destructive">{fieldErrors.persona.join(' ')}</p>
            )}
          </div>

          {/* Global errors */}
          {fieldErrors.non_field_errors && (
            <p className="text-sm text-destructive">{fieldErrors.non_field_errors.join(' ')}</p>
          )}
          {fieldErrors.detail && <p className="text-sm text-destructive">{fieldErrors.detail}</p>}

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

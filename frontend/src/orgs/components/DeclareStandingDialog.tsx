/**
 * DeclareStandingDialog (#3290) — a leader officially declares a persona favored
 * or disfavored with the org.
 *
 * Rides the generic REGISTRY action-dispatch seam (`POST
 * /api/actions/characters/{characterId}/dispatch/`, `useDispatchPlayerAction` /
 * `postDispatchAction` from `@/combat`) rather than a bespoke endpoint — the
 * same seam `PersonaContextMenu`'s Challenge/Identify menu items use for a
 * registry action with no `ActionTemplate`. Persona selection reuses the shared
 * debounced type-ahead (`usePersonaSearch`), the same pattern
 * `InviteToTableDialog` establishes.
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
import { Textarea } from '@/components/ui/textarea';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { usePersonaSearch } from '@/roster/usePersonaSearch';
import { useDispatchPlayerAction } from '@/combat/queries';
import { isDispatchFailure } from '@/combat/types';
import { useQueryClient } from '@tanstack/react-query';

interface PersonaOption {
  id: number;
  name: string;
}

interface DeclareStandingDialogProps {
  organizationId: number;
  organizationName: string;
  /** The declaring persona's ObjectDB/character pk — dispatch actor. */
  characterId: number;
  children: React.ReactNode;
}

export function DeclareStandingDialog({
  organizationId,
  organizationName,
  characterId,
  children,
}: DeclareStandingDialogProps) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [direction, setDirection] = useState<'favor' | 'disfavor'>('favor');
  const [personaQuery, setPersonaQuery] = useState('');
  const [selectedPersona, setSelectedPersona] = useState<PersonaOption | null>(null);
  const [citation, setCitation] = useState('');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const { mutateAsync: dispatchDeclare, isPending } = useDispatchPlayerAction(characterId);
  const { results, isFetching: personaSearching } = usePersonaSearch(personaQuery);
  const personaResults = selectedPersona?.name === personaQuery ? [] : results;

  function resetForm() {
    setDirection('favor');
    setPersonaQuery('');
    setSelectedPersona(null);
    setCitation('');
    setErrorMessage(null);
  }

  function handleOpenChange(next: boolean) {
    setOpen(next);
    if (!next) resetForm();
  }

  function handleSelectPersona(persona: PersonaOption) {
    setSelectedPersona(persona);
    setPersonaQuery(persona.name);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedPersona || !citation.trim()) return;
    setErrorMessage(null);

    try {
      const result = await dispatchDeclare({
        ref: { backend: 'registry', registry_key: 'declare_standing' },
        kwargs: {
          target: selectedPersona.id,
          organization_id: organizationId,
          direction,
          citation: citation.trim(),
        },
      });
      if (isDispatchFailure(result)) {
        setErrorMessage(result.message ?? 'That declaration was refused.');
        return;
      }
      toast.success(`${selectedPersona.name} declared ${direction}ed by ${organizationName}.`);
      queryClient
        .invalidateQueries({ queryKey: ['orgs', 'standingDeclarations', organizationId] })
        .catch(() => {});
      setOpen(false);
    } catch (err: unknown) {
      setErrorMessage(err instanceof Error ? err.message : 'That declaration failed.');
    }
  }

  const isValid = selectedPersona !== null && citation.trim().length > 0;

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger asChild>{children}</DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Declare Standing</DialogTitle>
          <DialogDescription>
            Officially declare a persona favored or disfavored by{' '}
            <strong>{organizationName}</strong>. Disfavor requires the target&apos;s antagonism
            consent; this is public and rate-limited to once per person per IC week.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={(e) => void handleSubmit(e)} className="space-y-4">
          <div className="space-y-1">
            <Label>Direction</Label>
            <RadioGroup
              value={direction}
              onValueChange={(value) => setDirection(value as 'favor' | 'disfavor')}
              className="flex gap-4"
            >
              <div className="flex items-center gap-2">
                <RadioGroupItem value="favor" id="standing-favor" />
                <Label htmlFor="standing-favor" className="font-normal">
                  Favor
                </Label>
              </div>
              <div className="flex items-center gap-2">
                <RadioGroupItem value="disfavor" id="standing-disfavor" />
                <Label htmlFor="standing-disfavor" className="font-normal">
                  Disfavor
                </Label>
              </div>
            </RadioGroup>
          </div>

          <div className="space-y-1">
            <Label htmlFor="standing-persona">Persona *</Label>
            <div className="relative">
              <Input
                id="standing-persona"
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
          </div>

          <div className="space-y-1">
            <Label htmlFor="standing-citation">Public citation *</Label>
            <Textarea
              id="standing-citation"
              value={citation}
              onChange={(e) => setCitation(e.target.value)}
              placeholder="Why is this declared?"
              rows={3}
            />
          </div>

          {errorMessage && <p className="text-sm text-destructive">{errorMessage}</p>}

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={!isValid || isPending}>
              {isPending ? 'Declaring…' : 'Declare'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

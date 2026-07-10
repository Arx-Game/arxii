/**
 * GuiseSheetDialog — author a cover persona's fabricated bio (#1682).
 *
 * The web face of the #1270 Guise Sheet: a cover/established persona needs its
 * OWN concept/quote/personality/background so the absence of a bio doesn't
 * instantly out it as fake. Prefills from the persona's current guise fields;
 * saving writes the full four-field state (clearing a field is a real edit).
 * Never offered for the PRIMARY face — the real bio lives on the sheet.
 */

import { useEffect, useState } from 'react';

import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';

import { useSetPersonaProfileMutation, type SwitchablePersona } from '../personaQueries';

interface GuiseSheetDialogProps {
  persona: SwitchablePersona;
  characterSheetId: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function GuiseSheetDialog({
  persona,
  characterSheetId,
  open,
  onOpenChange,
}: GuiseSheetDialogProps) {
  const save = useSetPersonaProfileMutation(characterSheetId);
  const [concept, setConcept] = useState(persona.guise_concept);
  const [quote, setQuote] = useState(persona.guise_quote);
  const [personality, setPersonality] = useState(persona.guise_personality);
  const [background, setBackground] = useState(persona.guise_background);

  // Re-prefill whenever the dialog opens (the persona's saved bio may have changed).
  useEffect(() => {
    if (open) {
      setConcept(persona.guise_concept);
      setQuote(persona.guise_quote);
      setPersonality(persona.guise_personality);
      setBackground(persona.guise_background);
      save.reset();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- prefill only on open/persona change
  }, [open, persona.id]);

  const submit = () => {
    save.mutate(
      { personaId: persona.id, body: { concept, quote, personality, background } },
      { onSuccess: () => onOpenChange(false) }
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Guise sheet — {persona.name}</DialogTitle>
          <DialogDescription>
            The bio this cover identity presents to the world. A guise with no story outs itself;
            give it one.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1">
            <Label htmlFor="guise-concept">Concept</Label>
            <Input
              id="guise-concept"
              value={concept}
              onChange={(e) => setConcept(e.target.value)}
              placeholder="Wandering scholar of little consequence"
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="guise-quote">Quote</Label>
            <Input
              id="guise-quote"
              value={quote}
              onChange={(e) => setQuote(e.target.value)}
              placeholder="A motto this identity lives by"
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="guise-personality">Personality</Label>
            <Textarea
              id="guise-personality"
              value={personality}
              onChange={(e) => setPersonality(e.target.value)}
              rows={3}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="guise-background">Background</Label>
            <Textarea
              id="guise-background"
              value={background}
              onChange={(e) => setBackground(e.target.value)}
              rows={4}
            />
          </div>
          {save.isError && (
            <p className="text-sm text-destructive">
              {save.error instanceof Error ? save.error.message : 'Could not save the guise sheet.'}
            </p>
          )}
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={save.isPending}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={save.isPending}>
            {save.isPending ? 'Saving…' : 'Save guise sheet'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

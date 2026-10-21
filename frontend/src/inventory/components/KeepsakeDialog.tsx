/**
 * KeepsakeDialog - declare an item a keepsake (#4530).
 *
 * The player chooses what it stands for (a tie, one of their deeds, a being, an organization,
 * a person or a place), writes one to three sentences in their own words, and chooses whether
 * examine shows them and whether the item is also marked treasured for consent. The points
 * come from the subject they choose; nobody scores the words.
 */

import { useState } from 'react';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/badge';
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
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { Textarea } from '@/components/ui/textarea';
import { usePersonaSearch } from '@/roster/usePersonaSearch';
import type { KeepsakeState, KeepsakeSubjectKind } from '../api';
import { useDeclareKeepsake } from '../hooks/useKeepsake';
import type { ItemInstance } from '../types';

const KINDS: { value: KeepsakeSubjectKind; label: string }[] = [
  { value: 'tie', label: 'a tie' },
  { value: 'deed', label: 'one of my deeds' },
  { value: 'being', label: 'a being' },
  { value: 'organization', label: 'an organization' },
  { value: 'person', label: 'a person' },
  { value: 'place', label: 'a place' },
];

/** The kinds whose subject is picked from the character's own list. */
type ListedKind = 'tie' | 'deed' | 'being' | 'organization';

const SUBJECT_LABEL: Record<KeepsakeSubjectKind, string> = {
  tie: 'Which tie',
  deed: 'Which deed',
  being: 'Which being',
  organization: 'Which organization',
  person: 'Which person',
  place: 'The place',
};

/** The pk picked from a listed kind's select, or undefined while nothing is chosen. */
function listedId(value: string): number | undefined {
  return value === '' ? undefined : Number(value);
}

interface SubjectFieldProps {
  kind: KeepsakeSubjectKind;
  options: { id: number; label: string }[];
  subjectId: string;
  onSubjectId: (value: string) => void;
  place: string;
  onPlace: (value: string) => void;
  person: { id: number; name: string } | null;
  onPerson: (value: { id: number; name: string } | null) => void;
  personQuery: string;
  onPersonQuery: (value: string) => void;
}

/** The part of the form that names the subject: free text for a place, a persona search for a
 * person, and a pick from the character's own list for everything else. */
function SubjectField({
  kind,
  options,
  subjectId,
  onSubjectId,
  place,
  onPlace,
  person,
  onPerson,
  personQuery,
  onPersonQuery,
}: SubjectFieldProps) {
  const { results, isFetching } = usePersonaSearch(personQuery, { enabled: kind === 'person' });
  if (kind === 'place') {
    return (
      <Input
        id="keepsake-subject"
        value={place}
        maxLength={100}
        onChange={(e) => onPlace(e.target.value)}
      />
    );
  }
  if (kind === 'person') {
    return (
      <>
        <Input
          id="keepsake-subject"
          placeholder="choose a persona"
          value={person ? person.name : personQuery}
          onChange={(e) => {
            onPerson(null);
            onPersonQuery(e.target.value);
          }}
        />
        {isFetching && <p className="text-xs text-muted-foreground">Searching...</p>}
        {!person && results.length > 0 && (
          <ul className="rounded-md border text-sm" aria-label="Matching personas">
            {results.map((persona) => (
              <li key={persona.id}>
                <button
                  type="button"
                  className="w-full px-3 py-1.5 text-left hover:bg-accent"
                  onClick={() => {
                    onPerson({ id: persona.id, name: persona.name });
                    onPersonQuery(persona.name);
                  }}
                >
                  {persona.name}
                </button>
              </li>
            ))}
          </ul>
        )}
      </>
    );
  }
  if (options.length === 0) {
    return (
      <p className="text-sm text-muted-foreground" data-testid="keepsake-no-subjects">
        You have none of these to choose from.
      </p>
    );
  }
  return (
    <select
      id="keepsake-subject"
      className="h-9 w-full rounded-md border bg-background px-2 text-sm"
      value={subjectId}
      onChange={(e) => onSubjectId(e.target.value)}
    >
      <option value="">Choose...</option>
      {options.map((option) => (
        <option key={option.id} value={option.id}>
          {option.label}
        </option>
      ))}
    </select>
  );
}

interface KeepsakeDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  item: ItemInstance;
  characterId: number;
  state: KeepsakeState;
}

export function KeepsakeDialog({
  open,
  onOpenChange,
  item,
  characterId,
  state,
}: KeepsakeDialogProps) {
  const [kind, setKind] = useState<KeepsakeSubjectKind>('deed');
  const [subjectId, setSubjectId] = useState<string>('');
  const [person, setPerson] = useState<{ id: number; name: string } | null>(null);
  const [personQuery, setPersonQuery] = useState('');
  const [place, setPlace] = useState('');
  const [text, setText] = useState('');
  const [shown, setShown] = useState(false);
  const [treasured, setTreasured] = useState(false);
  const declare = useDeclareKeepsake(characterId);

  const options = kind === 'person' || kind === 'place' ? [] : state.subjects[kind as ListedKind];
  const chosen = {
    id: kind === 'person' ? person?.id : listedId(subjectId),
    label: place.trim(),
  };
  const hasSubject = kind === 'place' ? chosen.label !== '' : chosen.id !== undefined;
  const canSave = hasSubject && text.trim() !== '' && !declare.isPending;

  function chooseKind(next: KeepsakeSubjectKind) {
    setKind(next);
    setSubjectId('');
    setPerson(null);
    setPersonQuery('');
  }

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!canSave) return;
    declare.mutate(
      {
        itemId: item.id,
        subjectKind: kind,
        subjectId: kind === 'place' ? undefined : chosen.id,
        subjectLabel: kind === 'place' ? chosen.label : undefined,
        text: text.trim(),
        shownOnExamine: shown,
        treasured,
      },
      {
        onSuccess: (result) => {
          if (result.success === false) {
            toast.error(result.message);
            return;
          }
          toast.success(result.message);
          setText('');
          onOpenChange(false);
        },
        onError: (error: Error) => toast.error(error.message),
      }
    );
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <form onSubmit={handleSubmit} className="space-y-4" data-testid="keepsake-form">
          <DialogHeader>
            <DialogTitle>{item.display_name}</DialogTitle>
            <DialogDescription>Keep this as a keepsake.</DialogDescription>
          </DialogHeader>
          {state.trophy_of.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {state.trophy_of.map((title) => (
                <Badge key={title} variant="secondary">
                  Trophy of {title}
                </Badge>
              ))}
            </div>
          )}

          <div className="space-y-2">
            <p className="text-sm font-medium">It stands for</p>
            <RadioGroup
              value={kind}
              onValueChange={(value) => chooseKind(value as KeepsakeSubjectKind)}
              className="flex flex-wrap gap-x-4 gap-y-2"
              data-testid="keepsake-kinds"
            >
              {KINDS.map((option) => (
                <div key={option.value} className="flex items-center gap-2">
                  <RadioGroupItem value={option.value} id={`keepsake-kind-${option.value}`} />
                  <Label htmlFor={`keepsake-kind-${option.value}`}>{option.label}</Label>
                </div>
              ))}
            </RadioGroup>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="keepsake-subject">{SUBJECT_LABEL[kind]}</Label>
            <SubjectField
              kind={kind}
              options={options}
              subjectId={subjectId}
              onSubjectId={setSubjectId}
              place={place}
              onPlace={setPlace}
              person={person}
              onPerson={setPerson}
              personQuery={personQuery}
              onPersonQuery={setPersonQuery}
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="keepsake-text">In your words (one to three sentences)</Label>
            <Textarea
              id="keepsake-text"
              value={text}
              maxLength={600}
              onChange={(e) => setText(e.target.value)}
            />
          </div>

          <div className="flex flex-col gap-1.5 text-sm">
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={shown} onChange={(e) => setShown(e.target.checked)} />
              Show on examine
            </label>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={treasured}
                onChange={(e) => setTreasured(e.target.checked)}
              />
              Also mark as treasured (staff ask you before it is put at stake)
            </label>
          </div>

          <p className="text-xs text-muted-foreground">
            Keepsakes: {state.status.used} of {state.status.limit} used. A keepsake counts{' '}
            {state.status.wait_days} days after you declare it. Its points come from the subject you
            choose. Nobody scores the words.
          </p>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={!canSave}>
              Save keepsake
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

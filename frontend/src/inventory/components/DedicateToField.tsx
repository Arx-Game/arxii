/**
 * DedicateToField - choose one other character a piece is made for (#4512).
 *
 * A dedication is written once and is permanent, so a piece that already has one shows
 * it and locks the choice. The choice is a type-ahead over personas; the character
 * making or commissioning the piece cannot be chosen (the server refuses it too).
 */

import { useState } from 'react';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { usePersonaSearch } from '@/roster/usePersonaSearch';

export interface DedicatePersona {
  id: number;
  name: string;
}

interface DedicateToFieldProps {
  /** Heading above the choice. */
  label: string;
  value: DedicatePersona | null;
  onChange: (persona: DedicatePersona | null) => void;
  /** The name the piece is already made for; locks the choice. */
  lockedTo?: string | null;
  /** The chooser's own name, left out of the results. */
  excludeName?: string | null;
  idPrefix: string;
}

export function DedicateToField({
  label,
  value,
  onChange,
  lockedTo,
  excludeName,
  idPrefix,
}: DedicateToFieldProps) {
  const [query, setQuery] = useState('');
  const { results, isFetching } = usePersonaSearch(query);
  const choices = (value?.name === query ? [] : results).filter((p) => p.name !== excludeName);
  const mode = value ? 'someone' : 'none';

  if (lockedTo) {
    return (
      <div className="space-y-1.5" data-testid={`${idPrefix}-dedication-locked`}>
        <p className="text-sm font-medium">{label}</p>
        <p className="text-sm">{lockedTo}</p>
        <p className="text-xs text-muted-foreground">
          This item already has a dedication, so this choice is locked. A dedication is permanent.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <p className="text-sm font-medium">{label}</p>
      <RadioGroup
        value={mode}
        onValueChange={(next) => {
          if (next === 'none') {
            onChange(null);
            setQuery('');
          }
        }}
        className="flex flex-wrap items-center gap-4"
      >
        <div className="flex items-center gap-2">
          <RadioGroupItem value="none" id={`${idPrefix}-for-none`} />
          <Label htmlFor={`${idPrefix}-for-none`}>no one</Label>
        </div>
        <div className="flex items-center gap-2">
          <RadioGroupItem value="someone" id={`${idPrefix}-for-someone`} disabled={!value} />
          <Label htmlFor={`${idPrefix}-for-someone`}>another character:</Label>
        </div>
      </RadioGroup>
      <Input
        id={`${idPrefix}-for-search`}
        aria-label="Choose a persona"
        placeholder="choose a persona"
        value={value ? value.name : query}
        onChange={(e) => {
          onChange(null);
          setQuery(e.target.value);
        }}
      />
      {isFetching && <p className="text-xs text-muted-foreground">Searching...</p>}
      {choices.length > 0 && (
        <ul className="rounded-md border text-sm" aria-label="Matching personas">
          {choices.map((persona) => (
            <li key={persona.id}>
              <button
                type="button"
                className="w-full px-3 py-1.5 text-left hover:bg-accent"
                onClick={() => {
                  onChange({ id: persona.id, name: persona.name });
                  setQuery(persona.name);
                }}
              >
                {persona.name}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

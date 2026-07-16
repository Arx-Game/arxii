/**
 * CharacterSearchField — debounced persona search field.
 *
 * Uses the shared `usePersonaSearch` hook (2026-07 audit) for debounced,
 * race-safe search. onChange is called with the selected persona id (number).
 */

import { useState, useEffect } from 'react';
import type React from 'react';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { usePersonaSearch } from '@/roster/usePersonaSearch';
import type { FieldProps } from '@/rituals/types';

interface PersonaOption {
  id: number;
  name: string;
}

export function CharacterSearchField({ field, value, onChange, disabled }: FieldProps) {
  const [query, setQuery] = useState('');
  const [selectedName, setSelectedName] = useState('');

  const { results, isFetching: searching } = usePersonaSearch(query);
  // Hide the dropdown once a selection is committed (query === selectedName).
  const showResults = selectedName !== query ? results : [];

  // Populate display name when value is provided externally
  useEffect(() => {
    if (value === null || value === '') {
      setSelectedName('');
      setQuery('');
    }
  }, [value]);

  function handleSelect(persona: PersonaOption) {
    setSelectedName(persona.name);
    setQuery(persona.name);
    onChange(persona.id);
  }

  function handleInputChange(e: React.ChangeEvent<HTMLInputElement>) {
    const next = e.target.value;
    setQuery(next);
    // Clear selection when user edits the input
    if (next !== selectedName) {
      setSelectedName('');
      onChange(null);
    }
  }

  return (
    <div className="space-y-2">
      <Label htmlFor={field.name}>{field.label}</Label>
      <div className="relative">
        <Input
          id={field.name}
          value={query}
          onChange={handleInputChange}
          placeholder="Search for a character…"
          autoComplete="off"
          disabled={disabled}
        />
        {searching && (
          <span className="absolute right-2 top-2 text-xs text-muted-foreground">Searching…</span>
        )}
        {showResults.length > 0 && (
          <ul className="absolute z-50 mt-1 max-h-48 w-full overflow-auto rounded-md border bg-popover shadow-lg">
            {showResults.map((p) => (
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
      {field.help && <p className="text-xs text-muted-foreground">{field.help}</p>}
    </div>
  );
}

/**
 * ResonancePickerField — dropdown of the caller's CharacterResonance rows.
 *
 * Calls GET /api/magic/character-resonances/?character_sheet=<pk> — scoped
 * to the authenticated user server-side AND narrowed to the active
 * character_sheet so users with alts see only the relevant character's
 * resonances. Each option's value is the CharacterResonance row id
 * (NOT the Resonance type id). Label is the resonance type name.
 *
 * NOTE: This file contains a one-off fetch hook. When Task 3.1 creates
 * frontend/src/magic/queries.ts, move useCharacterResonances there and
 * import it from that module.
 */

import { useQuery } from '@tanstack/react-query';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Label } from '@/components/ui/label';
import { apiFetch } from '@/evennia_replacements/api';
import type { components } from '@/generated/api';
import type { FieldProps } from '@/rituals/types';

type CharacterResonance = components['schemas']['CharacterResonance'];

async function fetchCharacterResonances(
  characterSheetId: number | undefined
): Promise<CharacterResonance[]> {
  const url =
    characterSheetId != null
      ? `/api/magic/character-resonances/?character_sheet=${characterSheetId}`
      : '/api/magic/character-resonances/';
  const res = await apiFetch(url);
  if (!res.ok) throw new Error('Failed to load character resonances');
  return res.json() as Promise<CharacterResonance[]>;
}

/** Temporary hook — move to frontend/src/magic/queries.ts when Task 3.1 lands. */
function useCharacterResonances(characterSheetId: number | undefined) {
  return useQuery({
    queryKey: ['character-resonances', characterSheetId ?? null],
    queryFn: () => fetchCharacterResonances(characterSheetId),
  });
}

export function ResonancePickerField({
  field,
  value,
  onChange,
  disabled,
  characterSheetId,
}: FieldProps) {
  const { data, isLoading } = useCharacterResonances(characterSheetId);
  const resonances = data ?? [];

  function handleChange(selectedValue: string) {
    onChange(Number(selectedValue));
  }

  return (
    <div className="space-y-2">
      <Label htmlFor={field.name}>{field.label}</Label>
      <Select
        value={value != null ? String(value) : ''}
        onValueChange={handleChange}
        disabled={disabled || isLoading}
      >
        <SelectTrigger id={field.name}>
          <SelectValue placeholder={isLoading ? 'Loading resonances…' : 'Select a resonance'} />
        </SelectTrigger>
        <SelectContent>
          {resonances.map((cr) => (
            <SelectItem key={cr.id} value={String(cr.id)}>
              {cr.resonance_name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      {field.help && <p className="text-xs text-muted-foreground">{field.help}</p>}
    </div>
  );
}

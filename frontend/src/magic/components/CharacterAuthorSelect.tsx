/**
 * CharacterAuthorSelect — alt picker for technique authoring (#774).
 *
 * Accounts that play more than one character must disambiguate which character
 * is authoring a technique; the backend validates the chosen `character_id`
 * against the account's owned set (TechniqueViewSet._resolve_owned_character).
 *
 * Renders nothing for accounts with 0 or 1 played characters so single-character
 * players keep the zero-click flow (the backend's single-character fallback
 * resolves the acting character on its own).
 */

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import type { MyRosterEntry } from '@/roster/types';

interface Props {
  /** The account's played characters (from useMyRosterEntriesQuery). */
  entries: MyRosterEntry[];
  /** Currently selected CharacterSheet PK, or null when none chosen yet. */
  value: number | null;
  /** Called with the chosen CharacterSheet PK. */
  onChange: (characterId: number) => void;
}

export function CharacterAuthorSelect({ entries, value, onChange }: Props) {
  // Single-character (or empty) accounts: no disambiguation needed.
  if (entries.length <= 1) return null;

  return (
    <div className="mb-6 w-72 space-y-1">
      <label htmlFor="technique-author-character" className="text-sm font-medium">
        Authoring as
      </label>
      <Select
        value={value != null ? String(value) : ''}
        onValueChange={(val) => onChange(Number(val))}
      >
        <SelectTrigger id="technique-author-character">
          <SelectValue placeholder="Select a character" />
        </SelectTrigger>
        <SelectContent>
          {entries.map((entry) => (
            <SelectItem key={entry.character_id} value={String(entry.character_id)}>
              {entry.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <p className="text-xs text-muted-foreground">
        You play multiple characters — choose which one is authoring this technique.
      </p>
    </div>
  );
}

export default CharacterAuthorSelect;

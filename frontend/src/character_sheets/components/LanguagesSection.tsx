/**
 * LanguagesSection (#2993 Task 8) — the character sheet's own-languages list.
 *
 * Ground truth, own sheet only: `useMyLanguages` (`/api/species/my-languages/`)
 * is self-scoped server-side to the viewer's own active character, so this
 * section is only meaningful — and only rendered — on `isMyCharacter`'s own
 * sheet (`CharacterSheetPage` gates it the same way it gates Updates/
 * Advancement/Clues).
 *
 * Drawn in the Reference Sheet's vocabulary (#3898): a glance list, and no heading of
 * its own — the sheet draws "Languages" above it.
 */

import { useMyLanguages } from '@/species/queries';
import { Glance } from '@/character_sheets/components/sheet/primitives';
import type { GlanceRow } from '@/character_sheets/components/sheet/primitives';

function capitalize(word: string): string {
  return word.length === 0 ? word : word[0].toUpperCase() + word.slice(1);
}

export function LanguagesSection() {
  const { data: languages } = useMyLanguages();
  const rows = languages ?? [];

  if (rows.length === 0) {
    return (
      <p className="refsheet-ledger" data-testid="languages-empty-state">
        No tongue but their own.
      </p>
    );
  }

  const glanceRows: GlanceRow[] = rows.map((row) => ({
    label: row.is_current ? `${row.name} (speaking)` : row.name,
    value: capitalize(row.band),
  }));

  return (
    <div data-testid="languages-list">
      <Glance rows={glanceRows} />
    </div>
  );
}

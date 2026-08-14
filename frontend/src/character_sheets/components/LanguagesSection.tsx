/**
 * LanguagesSection (#2993 Task 8) — the character sheet's own-languages list.
 *
 * Ground truth, own sheet only: `useMyLanguages` (`/api/species/my-languages/`)
 * is self-scoped server-side to the viewer's own active character, so this
 * section is only meaningful — and only rendered — on `isMyCharacter`'s own
 * sheet (`CharacterSheetPage` gates it the same way it gates Updates/
 * Advancement/Clues). Mirrors `MechanicsSection`'s empty-state/list pattern.
 */

import { useMyLanguages } from '@/species/queries';

function capitalize(word: string): string {
  return word.length === 0 ? word : word[0].toUpperCase() + word.slice(1);
}

export function LanguagesSection() {
  const { data: languages } = useMyLanguages();
  const rows = languages ?? [];

  return (
    <section>
      <h3 className="text-xl font-semibold">Languages</h3>
      {rows.length === 0 ? (
        <p className="text-sm text-muted-foreground" data-testid="languages-empty-state">
          No languages known.
        </p>
      ) : (
        <ul className="space-y-1" data-testid="languages-list">
          {rows.map((row) => (
            <li
              key={row.language_id}
              className="flex items-center justify-between gap-2"
              data-testid="language-row"
            >
              <span>
                {row.name}
                {row.is_current && (
                  <span className="ml-2 text-xs text-muted-foreground">(speaking)</span>
                )}
              </span>
              <span className="text-sm text-muted-foreground">{capitalize(row.band)}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

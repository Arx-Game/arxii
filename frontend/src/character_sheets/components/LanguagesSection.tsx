/**
 * LanguagesSection (#2993 Task 8; temporary rows #4090) — the character
 * sheet's own-languages list.
 *
 * Ground truth, own sheet only: `useMyLanguages` (`/api/species/my-languages/`)
 * is self-scoped server-side to the viewer's own active character, so this
 * section is only meaningful — and only rendered — on `isMyCharacter`'s own
 * sheet (`CharacterSheetPage` gates it the same way it gates Updates/
 * Advancement/Clues).
 *
 * Drawn in the Reference Sheet's vocabulary (#3898): a glance list, and no heading of
 * its own — the sheet draws "Languages" above it.
 *
 * A row raised by an active condition (#4090) shows the EFFECTIVE level, a
 * "Temporary" accent tag, and a gloss naming the condition
 * (`temporary_sources`). When the trained `fluency` is also above 0, the
 * gloss adds the trained band too ("from X · trained Broken") so the player
 * can see what they fall back to once the condition ends; a condition-only
 * row (no trained fluency at all) just names the condition, with no
 * "trained" text (Ruling Q1 on #4090 Task 11 — matches the approved demo,
 * Screen 3). The composer picker (`LanguageSelector`) and the sheet's
 * "Speaks" line both keep listing TRAINED languages only
 * (`fluency > 0`) — a condition grants understanding, never speech.
 */

import { useMyLanguages } from '@/species/queries';
import { Glance, Tag } from '@/character_sheets/components/sheet/primitives';
import type { GlanceRow } from '@/character_sheets/components/sheet/primitives';
import type { MyLanguage } from '@/species/types';

function capitalize(word: string): string {
  return word.length === 0 ? word : word[0].toUpperCase() + word.slice(1);
}

function levelValue(row: MyLanguage) {
  if (row.temporary_sources.length === 0) {
    return capitalize(row.effective_band);
  }
  const gloss =
    row.fluency > 0
      ? `from ${row.temporary_sources.join(', ')} · trained ${capitalize(row.band)}`
      : `from ${row.temporary_sources.join(', ')}`;
  return (
    <>
      {capitalize(row.effective_band)}
      <Tag accent>Temporary</Tag>
      <span className="refsheet-gloss">{gloss}</span>
    </>
  );
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
    value: levelValue(row),
  }));

  return (
    <div data-testid="languages-list">
      <Glance rows={glanceRows} />
    </div>
  );
}

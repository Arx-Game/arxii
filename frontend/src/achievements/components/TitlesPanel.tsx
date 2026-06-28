/**
 * TitlesPanel (#1522) — a character's earned, displayable titles.
 *
 * The web Titles tab, mirroring the telnet `sheet/titles` section. Titles are cosmetic and
 * public (a character shows them off), so the panel renders for any viewer. Each title is the
 * name of a TITLE-type reward attached to an achievement the character earned.
 */

import { Loader2 } from 'lucide-react';

import { useCharacterTitles } from '../queries';

interface Props {
  /** CharacterSheet pk (shared with the character ObjectDB pk). */
  characterSheetId: number;
}

export function TitlesPanel({ characterSheetId }: Props) {
  const { data: titles, isLoading } = useCharacterTitles(characterSheetId);

  if (isLoading) {
    return (
      <div className="flex justify-center py-8">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!titles || titles.length === 0) {
    return (
      <p className="py-8 text-center text-muted-foreground" data-testid="titles-empty-state">
        No titles earned yet.
      </p>
    );
  }

  return (
    <ul className="space-y-2" data-testid="titles-list">
      {titles.map((title) => (
        <li
          key={title.id}
          className="flex items-center justify-between rounded-lg border bg-card p-3"
          data-testid="title-row"
        >
          <span className="font-medium">{title.title}</span>
          <span className="text-xs text-muted-foreground">
            {new Date(title.earned_at).toLocaleDateString()}
          </span>
        </li>
      ))}
    </ul>
  );
}

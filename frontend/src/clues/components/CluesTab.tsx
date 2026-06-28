/**
 * CluesTab (#1575) — a character's held-clue journal.
 *
 * The clues this character has discovered, newest first. Private IC knowledge — only rendered for
 * the player's own character. Each clue shows its player-visible name + description; the *target*
 * it points at is the separate discovery/research layer, not shown here.
 */

import { Loader2 } from 'lucide-react';

import { useHeldClues } from '../queries';

interface Props {
  /** CharacterSheet pk (shared with the character ObjectDB pk). */
  characterSheetId: number;
}

export function CluesTab({ characterSheetId }: Props) {
  const { data: clues, isLoading } = useHeldClues(characterSheetId);

  if (isLoading) {
    return (
      <div className="flex justify-center py-8">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!clues || clues.length === 0) {
    return (
      <p className="py-8 text-center text-muted-foreground" data-testid="clues-empty-state">
        No clues discovered yet. Search the world and follow what you find.
      </p>
    );
  }

  return (
    <ul className="space-y-3" data-testid="clues-list">
      {clues.map((clue) => (
        <li key={clue.id} className="rounded-lg border bg-card p-4" data-testid="clue-row">
          <div className="flex items-baseline justify-between gap-3">
            <h4 className="font-medium">{clue.name}</h4>
            <span className="shrink-0 text-xs text-muted-foreground">
              {new Date(clue.found_at).toLocaleDateString()}
            </span>
          </div>
          <p className="mt-1 whitespace-pre-line text-sm text-muted-foreground">
            {clue.description}
          </p>
        </li>
      ))}
    </ul>
  );
}

/**
 * CluesTab (#1575) — a character's held-clue journal.
 *
 * The clues this character has discovered, newest first. Private IC knowledge — only rendered for
 * the player's own character. Each clue shows its player-visible name + description; the *target*
 * it points at is the separate discovery/research layer, not shown here.
 *
 * Drawn in the Reference Sheet's vocabulary (#3898): entries on hairlines rather than
 * bordered cards, so a long journal reads as an index instead of a stack.
 */

import { useHeldClues } from '../queries';
import { Entries, Entry, Ledger } from '@/character_sheets/components/sheet/primitives';

interface Props {
  /** CharacterSheet pk (shared with the character ObjectDB pk). */
  characterSheetId: number;
}

export function CluesTab({ characterSheetId }: Props) {
  const { data: clues, isLoading } = useHeldClues(characterSheetId);

  if (isLoading) {
    return <Ledger>Reading what they have found…</Ledger>;
  }

  if (!clues || clues.length === 0) {
    return (
      <p className="refsheet-ledger" data-testid="clues-empty-state">
        Nothing found yet. Search the world and follow what you find.
      </p>
    );
  }

  return (
    <div data-testid="clues-list">
      <Entries>
        {clues.map((clue) => (
          <div key={clue.id} data-testid="clue-row">
            <Entry
              name={clue.name}
              aside={
                <span className="refsheet-note">
                  {new Date(clue.found_at).toLocaleDateString()}
                </span>
              }
              gloss={<span style={{ whiteSpace: 'pre-line' }}>{clue.description}</span>}
            />
          </div>
        ))}
      </Entries>
    </div>
  );
}

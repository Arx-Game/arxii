/**
 * TitlesPanel (#1522, #3466) — a persona's earned, displayable titles.
 *
 * The web Titles tab, mirroring the telnet `sheet/titles` section. Titles are cosmetic and
 * public (a character shows them off), so the panel renders for any viewer. Each title is
 * either the name of a TITLE-type reward attached to an achievement, or a deed's own name —
 * always the one PERSONA (face) that earned it, never the character sheet as a whole.
 *
 * Drawn in the Reference Sheet's vocabulary (#3898): entries on hairlines with the date
 * earned pulled right, rather than a stack of bordered tiles.
 */

import { usePersonaTitles } from '../queries';
import { Entries, Entry, Ledger } from '@/character_sheets/components/sheet/primitives';

interface Props {
  /** Persona pk whose titles to show; null while the caller hasn't resolved one yet. */
  personaId: number | null;
}

export function TitlesPanel({ personaId }: Props) {
  const { data: titles, isLoading } = usePersonaTitles(personaId);

  if (isLoading) {
    return <Ledger>Reading their titles…</Ledger>;
  }

  if (!titles || titles.length === 0) {
    return (
      <p className="refsheet-ledger" data-testid="titles-empty-state">
        No title yet, earned or granted.
      </p>
    );
  }

  return (
    <div data-testid="titles-list">
      <Entries>
        {titles.map((title) => (
          <div key={title.id} data-testid="title-row">
            <Entry
              name={title.title}
              aside={
                <span className="refsheet-note">
                  {new Date(title.earned_at).toLocaleDateString()}
                </span>
              }
            />
          </div>
        ))}
      </Entries>
    </div>
  );
}

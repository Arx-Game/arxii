/**
 * The cast (#3957) — every tie this character has, one face each.
 *
 * Built from the SHEET payload rather than from the ties API, because the payload is
 * the only source already shaped for the viewer: the server decided which cards this
 * reader gets, which labels are on them, and whether there are numbers to print. A cast
 * built client-side from the caller's own list would be empty for exactly the visitor
 * this page holds its shape for.
 *
 * So there is no audience branch here beyond reading the nulls the payload sent. A card
 * whose `depth` is null belongs to a reader who may not know it, and it prints the
 * summary line where the numbers would have been.
 *
 * Render-or-vanish, the sheet's rule: a visitor looking at a character with no visible
 * ties gets nothing at all rather than an empty-state card. The owner keeps the ledger
 * line, because it is the way in to declaring the first one.
 */

import { Link } from 'react-router-dom';
import type { CharacterSheetTie } from '@/character_sheets/api';
import { Ledger, Stack } from '@/character_sheets/components/sheet/primitives';
import { labelTagClass, labelText, mutualSuffix } from './labelText';

export interface TieCastProps {
  ties: CharacterSheetTie[];
  /** The VIEWED character's RosterEntry id — every tie page hangs off it. */
  entryId: number;
  isMyCharacter: boolean;
  /** AP set across every tie this week; null for anyone but the owner and staff. */
  apThisWeek: number | null;
}

export function TieCast({ ties, entryId, isMyCharacter, apThisWeek }: TieCastProps) {
  if (ties.length === 0 && !isMyCharacter) return null;

  const count = `${ties.length} ${ties.length === 1 ? 'tie' : 'ties'}`;
  const ledger = apThisWeek == null ? count : `${count} · ${apThisWeek} AP this week`;

  return (
    <Stack>
      <Ledger>
        <span>{ledger}</span>
        {isMyCharacter && (
          <>
            {' '}
            <Link to={`/characters/${entryId}/ties/new`}>Declare a tie</Link>
          </>
        )}
      </Ledger>
      {ties.length > 0 && (
        <div className="refsheet-cast">
          {ties.map((tie) => (
            <div key={tie.relationship_id} className="refsheet-face">
              <span className="refsheet-face-ring" aria-hidden="true" />
              <span className="refsheet-face-who">
                <Link to={`/characters/${entryId}/ties/${tie.relationship_id}`}>
                  {tie.other_name}
                </Link>
              </span>
              {tie.labels.length > 0 && (
                <div className="refsheet-tags">
                  {tie.labels.map((label) => (
                    <span key={label.label_id} className={labelTagClass(label, label.valence)}>
                      {labelText(label)}
                      {mutualSuffix(label)}
                    </span>
                  ))}
                </div>
              )}
              {tie.depth != null ? (
                <span className="refsheet-face-how">
                  Depth {tie.depth} · Tier {tie.tier}
                </span>
              ) : (
                tie.summary_line && <span className="refsheet-face-how">{tie.summary_line}</span>
              )}
              {tie.thread && <span className="refsheet-face-thread">{tie.thread}</span>}
            </div>
          ))}
        </div>
      )}
    </Stack>
  );
}

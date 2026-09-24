/**
 * The tie's night plate (#3957) — who this is, and what they are to this character.
 *
 * ONE SIDE. The other person's page is on their own sheet, and nothing here is a
 * negotiation: the labels are what this character says, the summary is what this
 * character wrote, and the tier is this character's own claim.
 *
 * Everything the viewer may not know arrives null and is simply not drawn. The eyebrow
 * naming the side's owner is for the two parties, because to a stranger this page is
 * about one person and the "X and" framing implies a viewer in the room.
 */

import { useState } from 'react';

import { Eyebrow, QuietDoor } from '@/character_sheets/components/sheet/primitives';
import { useSetTieSummary } from '@/relationships/queries';
import { hasTieTarget, tieTargetRef, type Tie } from '../api';
import { DepthReadout } from './DepthReadout';
import { labelTagClass, labelText, mutualSuffix } from './labelText';

export interface TiePlateProps {
  tie: Tie;
  /** The character whose side this is. Drawn only for the two parties. */
  ownerName: string | null;
  /**
   * Whether this side belongs to the viewer's own character — `tie.is_own_side`, never a
   * reading of `audience`. Staff reading someone else's tie are STAFF but do not own it,
   * and the summary write resolves its side from the CALLER's sheet, so an Edit door
   * offered on the audience enum wrote the staff character's own summary (#3957 review).
   */
  isOwnSide: boolean;
  targetPersonaId: number | null;
}

export function TiePlate({ tie, ownerName, isOwnSide, targetPersonaId }: TiePlateProps) {
  const isParty = tie.audience !== 'third_party';
  const target = tieTargetRef(tie, targetPersonaId);
  const canWrite = hasTieTarget(target);
  const setSummary = useSetTieSummary();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(tie.summary);
  const [error, setError] = useState<string | null>(null);

  function save() {
    setError(null);
    setSummary.mutate(
      { ...target, summary: draft },
      {
        onSuccess: () => setEditing(false),
        onError: (err: Error) => setError(err.message),
      }
    );
  }

  return (
    <div className="refsheet-plate refsheet-plate-solo">
      <div className="refsheet-plate-body">
        <div className="refsheet-plate-head">
          <div>
            {isParty && ownerName && <Eyebrow>{ownerName} and</Eyebrow>}
            <h2 className="refsheet-heading">{tie.target_name}</h2>
          </div>
          <DepthReadout tie={tie} />
        </div>

        {tie.labels.length > 0 && (
          <div className="refsheet-tags">
            {tie.labels.map((label) => (
              <span
                key={label.id}
                className={labelTagClass(
                  { ...label, is_former: label.ended_at !== null },
                  label.type_valence
                )}
              >
                {labelText({ ...label, is_former: label.ended_at !== null })}
                {mutualSuffix({ ...label, is_former: label.ended_at !== null })}
              </span>
            ))}
          </div>
        )}

        {/* Render-or-vanish: a stranger on a tie whose owner has written nothing gets no
            bare Summary heading with empty space under it. */}
        {(isOwnSide || tie.summary) && (
          <div className="refsheet-plate-summary">
            <Eyebrow>Summary</Eyebrow>
            {isOwnSide && !editing && (
              <QuietDoor
                onClick={() => {
                  setDraft(tie.summary);
                  setEditing(true);
                }}
              >
                Edit
              </QuietDoor>
            )}
          </div>
        )}
        {editing ? (
          <>
            <textarea
              aria-label="Summary"
              className="refsheet-input"
              rows={6}
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
            />
            {error && (
              <p role="alert" className="refsheet-note refsheet-error">
                {error}
              </p>
            )}
            <div className="refsheet-doors">
              <QuietDoor onClick={save} disabled={!canWrite || setSummary.isPending}>
                Save
              </QuietDoor>
              <QuietDoor onClick={() => setEditing(false)}>Keep as is</QuietDoor>
            </div>
          </>
        ) : (
          tie.summary && <p className="refsheet-plate-prose">{tie.summary}</p>
        )}

        {isParty && (
          <div className="refsheet-plate-soft">
            Thread:{' '}
            {tie.thread ? `level ${tie.thread.level}, ${tie.thread.resonance_name}` : 'none yet.'}
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * Labels and AP (#3957) — the owner's own side, written.
 *
 * Three rules are enforced by what this block DRAWS rather than by anything it checks:
 *
 * - Awareness moves one way. A private label offers Make clandestine and Make public;
 *   a clandestine one offers only Make public; a public one offers neither. The
 *   backward move is not disabled here, it is never rendered, so there is nothing to
 *   discover. (The service refuses it either way — this is the interface agreeing.)
 * - Nothing deletes. End stamps the row and it stays on the card as former; Change ends
 *   one and declares its replacement. There is no third door.
 * - A former label has no doors at all. It is a thing that happened.
 *
 * AP is ONE number for the whole tie, not one per label — the point of the redesign.
 * The week's budget is not on the tie payload, so the field stands alone rather than
 * printing a total this block would have to go and fetch to be honest about.
 */

import { useState } from 'react';

import { formatIcDate } from '@/journals/dates';
import { Entries, Entry, Eyebrow, QuietDoor } from '@/character_sheets/components/sheet/primitives';
import { useAdvanceAwareness, useEndLabel, useSetTieAllocation } from '@/relationships/queries';
import { tieTargetRef, type Tie, type TieLabel } from '../api';
import { labelTagClass, labelText } from './labelText';
import { RelationshipShift } from './RelationshipShift';
import { TypePicker } from './TypePicker';

/** `Clandestine · since 1 September 1012`, or just the date where there is no marker. */
function awarenessLine(label: TieLabel): string {
  const since = `since ${formatIcDate(label.since)}`;
  if (label.awareness === 'clandestine') return `Clandestine · ${since}`;
  if (label.awareness === 'private') return `Private · ${since}`;
  return since;
}

export interface LabelsAndApProps {
  tie: Tie;
  /** The other side's persona pk — what every tie write names its target by. */
  targetPersonaId: number | null;
}

export function LabelsAndAp({ tie, targetPersonaId }: LabelsAndApProps) {
  const target = tieTargetRef(tie, targetPersonaId);
  const setAllocation = useSetTieAllocation();
  const endLabel = useEndLabel();
  const advanceAwareness = useAdvanceAwareness();

  const [ap, setAp] = useState(String(tie.ap_this_week ?? 0));
  const [shifting, setShifting] = useState<TieLabel | null>(null);
  const [picking, setPicking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const open = tie.labels.filter((label) => label.ended_at === null);

  function report(err: Error) {
    setError(err.message);
  }

  function keepAp() {
    setError(null);
    setAllocation.mutate({ ...target, ap_amount: Number(ap) || 0 }, { onError: report });
  }

  function end(label: TieLabel) {
    if (!window.confirm(`End ${label.type_name}?`)) return;
    setError(null);
    endLabel.mutate({ label_id: label.id }, { onError: report });
  }

  function move(label: TieLabel, to: 'clandestine' | 'public') {
    setError(null);
    advanceAwareness.mutate({ label_id: label.id, awareness: to }, { onError: report });
  }

  return (
    <div className="refsheet-block">
      {/* An eyebrow, not a heading: the plate above already names them in an h2, and a
          second one at the same weight reads as a duplicate to anyone hearing the page. */}
      <Eyebrow>{tie.target_name}</Eyebrow>
      {error && (
        <p role="alert" className="refsheet-note refsheet-error">
          {error}
        </p>
      )}

      <div className="refsheet-doors">
        <div className="refsheet-field">
          <label htmlFor="tie-ap">AP this week</label>
          <input
            id="tie-ap"
            className="refsheet-input"
            inputMode="numeric"
            value={ap}
            onChange={(event) => setAp(event.target.value)}
          />
        </div>
        <QuietDoor onClick={keepAp} disabled={setAllocation.isPending}>
          Keep
        </QuietDoor>
      </div>

      <Entries>
        {tie.labels.map((label) => {
          const former = label.ended_at !== null;
          return (
            <Entry
              key={label.id}
              name={label.type_name}
              aside={<span className="refsheet-note">{awarenessLine(label)}</span>}
              tags={
                former ? (
                  <span className={labelTagClass(label, label.type_valence)}>
                    {labelText({ ...label, is_former: true })}
                  </span>
                ) : undefined
              }
              gloss={label.replaced_type_name ? `Replaced ${label.replaced_type_name}` : undefined}
            >
              {!former && (
                <div className="refsheet-doors">
                  <QuietDoor onClick={() => setShifting(label)}>Change</QuietDoor>
                  <QuietDoor onClick={() => end(label)} disabled={endLabel.isPending}>
                    End
                  </QuietDoor>
                  {label.awareness === 'private' && (
                    <QuietDoor
                      onClick={() => move(label, 'clandestine')}
                      disabled={advanceAwareness.isPending}
                    >
                      Make clandestine
                    </QuietDoor>
                  )}
                  {label.awareness !== 'public' && (
                    <QuietDoor
                      onClick={() => move(label, 'public')}
                      disabled={advanceAwareness.isPending}
                    >
                      Make public
                    </QuietDoor>
                  )}
                </div>
              )}
            </Entry>
          );
        })}
      </Entries>

      {shifting && <RelationshipShift label={shifting} onDone={() => setShifting(null)} />}

      <div className="refsheet-doors">
        <QuietDoor expanded={picking} onClick={() => setPicking((was) => !was)}>
          Declare another
        </QuietDoor>
      </div>
      {picking && (
        <TypePicker
          target={target}
          heldTypeIds={open.map((label) => label.type)}
          onDeclared={() => setPicking(false)}
        />
      )}
    </div>
  );
}

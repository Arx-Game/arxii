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
 * Beside it stands the week's whole purse, `remaining / total`, which the tie payload
 * now carries (`ap_pool`, owner-only): the approved design puts it there because it is
 * what tells a player whether they may spend on this tie at all, and a field with no
 * budget beside it makes them go and look somewhere else to find out.
 */

import { useState } from 'react';

import { Entries, Entry, Eyebrow, QuietDoor } from '@/character_sheets/components/sheet/primitives';
import { useAdvanceAwareness, useEndLabel, useSetTieAllocation } from '@/relationships/queries';
import { hasTieTarget, tieTargetRef, type Tie, type TieLabel } from '../api';
import { labelTagClass, labelText } from './labelText';
import { RelationshipShift } from './RelationshipShift';
import { TypePicker } from './TypePicker';

/**
 * The line beside a label's name: its marker, and nothing else.
 *
 * No date. `RelationshipLabel.since` is a `DateTimeField(default=timezone.now)` — a real
 * posting timestamp — and printing it beside an in-character label spelled it in the
 * world's voice ("since 21 September 2026"). A label is a thing that is true now, not a
 * receipt, so the marker is the whole of what the row has to say. A public label says
 * nothing at all, which is the awareness rule everywhere else in this feature.
 *
 * A former label prints only `former`: the awareness of an ended label is not a live
 * fact, and the chip beside it already carries the same word.
 */
function awarenessLine(label: TieLabel): string {
  if (label.ended_at !== null) return 'former';
  if (label.awareness === 'clandestine') return 'Clandestine';
  if (label.awareness === 'private') return 'Private';
  return '';
}

export interface LabelsAndApProps {
  tie: Tie;
  /** The other side's persona pk — what every tie write names its target by. */
  targetPersonaId: number | null;
}

export function LabelsAndAp({ tie, targetPersonaId }: LabelsAndApProps) {
  const target = tieTargetRef(tie, targetPersonaId);
  const canWrite = hasTieTarget(target);
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
    // No confirm dialog (#3957 final review): ending a label deletes nothing — the row
    // stays as former — so there is nothing to guard against, and the browser's own
    // modal is chrome in a surface whose copy is otherwise bare.
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
        {/* Bare numbers, no label: the field beside them already says what they count,
            and the pool vanishes rather than printing a zero for a viewer who is not
            the owner (nobody else is ever shown this block, but the null is the
            server's answer and the block reads it rather than assuming). */}
        {tie.ap_pool && (
          <span className="refsheet-note">
            {tie.ap_pool.remaining} / {tie.ap_pool.total}
          </span>
        )}
        <QuietDoor onClick={keepAp} disabled={!canWrite || setAllocation.isPending}>
          Keep
        </QuietDoor>
      </div>

      <Entries>
        {tie.labels.map((label) => {
          const former = label.ended_at !== null;
          const marker = awarenessLine(label);
          return (
            <Entry
              key={label.id}
              name={label.type_name}
              aside={marker ? <span className="refsheet-note">{marker}</span> : undefined}
              tags={
                former ? (
                  <span
                    className={labelTagClass({ ...label, is_former: true }, label.type_valence)}
                  >
                    {labelText({ ...label, is_former: true })}
                  </span>
                ) : undefined
              }
              gloss={label.replaced_type_name ? `Replaced ${label.replaced_type_name}` : undefined}
            >
              {/* The note the owner left when they changed this label into what it is.
                  The server ships `note` to the owner and staff only, and this whole
                  block renders only on the viewer's own side, so it is read exactly
                  where it was written and nowhere else. Bare text: it is the player's
                  own sentence, not a field the interface is labelling. */}
              {label.note && <p className="refsheet-entry-gloss">{label.note}</p>}
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

      {shifting && (
        <RelationshipShift
          label={shifting}
          heldTypeIds={open.map((label) => label.type)}
          onDone={() => setShifting(null)}
        />
      )}

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

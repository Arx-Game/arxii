/**
 * BaronyPage (#3983 Task 9, plate S-VI's barony sub-page, shown beneath the
 * barony table for the disclosed row) — prose, hall, land-shape chips, an
 * Atlas link, and a read-only produces ledger.
 *
 * Only `description` is a `useDraft` textarea (the "draft kept as you type"
 * field the plate's savebar note describes) — `hall` and the land-shape
 * chips are short, low-effort-to-retype fields staged as plain local state
 * instead, the same choice `HouseChapter` makes for `state`.
 *
 * Two stated gaps:
 * - the plate's `.chain` ancestry breadcrumb (kingdom > duchy > county >
 *   barony) can't be built past two links — `AlmanachBarony.in` gives only
 *   the barony's own immediate parent Area name, not the full chain up to
 *   the realm; the chain here renders just `[in, barony]` rather than
 *   fabricating the missing ancestors.
 * - the produces ledger's rows (holding name/kind/materials/gross-per-cycle)
 *   have no backing field anywhere in `HouseDocument` — `lands.produces` is
 *   a flat, HOUSE-wide list of holding KIND names (`_lands_payload`,
 *   `almanach_reads.py`), never a per-barony `DomainHolding` breakdown — so
 *   the ledger renders its headers with an honest "no holdings on record"
 *   body rather than misattributing the house-wide list to this one barony.
 *   "⊕ a holding" is the fourth pre-approved omission (holding kinds aren't
 *   on the wire either) — rendered as an inert door.
 */
import { useEffect, useState } from 'react';

import { useDraft } from '@/world-builder/document/useDraft';

import { useLandShapes } from '../queries';
import type { AlmanachBarony } from '../types';

export interface DescribeDemesneFields {
  description: string;
  hall_name: string;
  land_shape_names: string[];
}

export interface BaronyPageProps {
  barony: AlmanachBarony;
  onSave: (fields: DescribeDemesneFields) => void;
}

export function BaronyPage({ barony, onSave }: BaronyPageProps) {
  const { data: landShapesPayload } = useLandShapes();
  const landShapes = landShapesPayload?.results ?? [];
  const description = useDraft(barony.id, 'barony-description', barony.description);
  const [hall, setHall] = useState(barony.hall);
  const [shapes, setShapes] = useState<string[]>(barony.land_shapes);
  const hallId = `barony-hall-${barony.id}`;

  // A different barony's page re-seeds hall/shapes from its own data — the
  // previous barony's in-progress edit must never bleed into this one.
  useEffect(() => {
    setHall(barony.hall);
    setShapes(barony.land_shapes);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [barony.id]);

  const save = () => {
    onSave({
      description: description.value,
      hall_name: hall,
      land_shape_names: shapes,
    });
    description.clearDraft();
  };

  return (
    <>
      <h4 className="sec">
        {barony.name} <span className="tier">barony{barony.is_seat ? ' · seat' : ''}</span>
      </h4>
      <div className="chain">
        {barony.in !== '' && (
          <span>
            <span className="tw">in</span>
            {barony.in}
          </span>
        )}
        <span className="cur">
          <span className="tw">barony</span>
          {barony.name}
        </span>
      </div>
      <label htmlFor={`barony-description-${barony.id}`} className="sr-only">
        description
      </label>
      <textarea
        id={`barony-description-${barony.id}`}
        className="prose"
        value={description.value}
        onChange={(event) => description.setValue(event.target.value)}
      />
      <div className="row3">
        <div className="field">
          <label htmlFor={hallId}>hall</label>
          <input
            id={hallId}
            type="text"
            value={hall}
            onChange={(event) => setHall(event.target.value)}
          />
        </div>
        <div className="field">
          <span className="label">land</span>
          <div className="chips" role="group" aria-label="Land shapes">
            {landShapes.map((shape) => {
              const pressed = shapes.includes(shape.name);
              return (
                <button
                  key={shape.id}
                  type="button"
                  className={pressed ? 'chip acc' : 'chip'}
                  aria-pressed={pressed}
                  onClick={() =>
                    setShapes(
                      pressed
                        ? shapes.filter((name) => name !== shape.name)
                        : [...shapes, shape.name]
                    )
                  }
                >
                  {shape.name}
                </button>
              );
            })}
          </div>
        </div>
        <div className="field">
          <span className="label">population</span>
          <div className="val">
            {barony.population > 0 ? barony.population : <abbr title="none">—</abbr>}
          </div>
        </div>
      </div>
      <div className="field">
        <span className="label">on the Atlas</span>
        <div className="val">
          <a href="/staff/world-builder">open on the Atlas</a>
        </div>
      </div>
      <div className="field">
        <span className="label">produces</span>
        <div className="scroll">
          <table className="ledger">
            <thead>
              <tr>
                <th scope="col">holding</th>
                <th scope="col">kind</th>
                <th scope="col">materials</th>
                <th scope="col" className="n">
                  gross / cycle
                </th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td colSpan={4} className="faint">
                  no holdings on record
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <button
          type="button"
          className="add"
          disabled
          title="holding kinds aren't available to pick from yet"
        >
          ⊕ a holding
        </button>
      </div>
      <div className="savebar">
        <span className="note">draft kept as you type</span>
        <button type="button" className="btn" onClick={save}>
          Save
        </button>
      </div>
    </>
  );
}

/**
 * LandsLeaf (#3983 Task 9, plate S-VI "Lands") — opens folded: one line for
 * the house (seat/produces/population), then its baronies as `.lad` rows,
 * wherever they lie; a `<button aria-expanded>` disclosure opens
 * `BaronyPage` beneath the table for the selected row (only one open at a
 * time, matching the plate's single-barony-page example).
 *
 * The plate's third row3 field is "prosperity" — no such field exists
 * anywhere in `AlmanachDocumentLands`/`AlmanachBarony` (a Domain-level
 * game-balance stat this payload never surfaces), so that slot shows
 * `population` instead, a real field the payload does carry.
 */
import { useState } from 'react';

import { BaronyPage } from './BaronyPage';
import type { AlmanachDocumentLands } from '../types';
import type { DescribeDemesneFields } from './BaronyPage';

export interface LandsLeafProps {
  houseName: string;
  lands: AlmanachDocumentLands;
  onDescribe: (domainId: number, fields: DescribeDemesneFields) => void;
}

export function LandsLeaf({ houseName, lands, onDescribe }: LandsLeafProps) {
  // Folded by default — nothing expanded until a row's own disclosure
  // button is clicked. The plate's own screenshot happens to show Perdition
  // already open as an illustrative example, but "opens folded" (the
  // plate's own caption) is the live default this leaf renders.
  const [openDomainId, setOpenDomainId] = useState<number | null>(null);

  return (
    <main className="chapter">
      <h3>
        Lands of {houseName} <span className="tier">{lands.count} baronies</span>
      </h3>
      <div className="row3">
        <div className="field">
          <span className="label">seat</span>
          <div className="val">{lands.seat !== '' ? lands.seat : <abbr title="none">—</abbr>}</div>
        </div>
        <div className="field">
          <span className="label">produces</span>
          <div className="val">
            {lands.produces.length > 0 ? lands.produces.join(' · ') : <abbr title="none">—</abbr>}
          </div>
        </div>
        <div className="field">
          <span className="label">population</span>
          <div className="val">
            {lands.population > 0 ? lands.population : <abbr title="none">—</abbr>}
          </div>
        </div>
      </div>
      <div className="scroll">
        <table className="lad">
          <thead>
            <tr>
              <th scope="col">barony</th>
              <th scope="col">in</th>
              <th scope="col">hall</th>
              <th scope="col" className="n">
                population
              </th>
            </tr>
          </thead>
          <tbody>
            {lands.baronies.map((barony) => {
              const expanded = openDomainId === barony.id;
              return (
                <tr key={barony.id} className={expanded ? 'sel' : undefined}>
                  <td>
                    <button
                      type="button"
                      className="tg"
                      aria-expanded={expanded}
                      aria-label={`${expanded ? 'Collapse' : 'Expand'} ${barony.name}`}
                      onClick={() => setOpenDomainId(expanded ? null : barony.id)}
                    >
                      {expanded ? '▾' : '▸'}
                    </button>
                    {barony.name}
                    {barony.is_seat && <span className="seat">seat of {houseName}</span>}
                  </td>
                  <td>{barony.in !== '' ? barony.in : <abbr title="none">—</abbr>}</td>
                  <td>
                    {barony.hall !== '' ? (
                      barony.hall
                    ) : (
                      <span className="chip undef">Undefined</span>
                    )}
                  </td>
                  <td className="n">
                    {barony.population > 0 ? barony.population : <abbr title="none">—</abbr>}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {openDomainId != null &&
        (() => {
          const barony = lands.baronies.find((b) => b.id === openDomainId);
          return barony ? (
            <BaronyPage barony={barony} onSave={(fields) => onDescribe(barony.id, fields)} />
          ) : null;
        })()}
    </main>
  );
}

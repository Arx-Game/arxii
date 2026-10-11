/**
 * Books, Forces and Openings (#4239): the three chapters the house, domain and
 * crime pages share. Numbers bare, in coppers per cycle; the full ledger is
 * #4243 and these read what exists until it.
 */
import { Link } from 'react-router-dom';

import type { AlmanachBooks, AlmanachForceRow, AlmanachOpenings } from '../types';
import { personUrl, statusMark, tierMark } from './tier';

export function Books({ books }: { books: AlmanachBooks }) {
  return (
    <>
      <h4 className="sec">Books</h4>
      <div className="row3">
        <div className="field">
          <span className="label">income</span>
          <div className="val">
            {books.income_week.toLocaleString()} c / week
            <span className="meta"> {books.streams} streams</span>
          </div>
        </div>
        <div className="field">
          <span className="label">uncollected</span>
          <div className="val">{books.uncollected.toLocaleString()} c</div>
        </div>
        <div className="field">
          <span className="label">treasury</span>
          <div className="val">{books.treasury.toLocaleString()} c</div>
        </div>
      </div>
    </>
  );
}

export function Forces({ forces }: { forces: AlmanachForceRow[] }) {
  return (
    <>
      <h4 className="sec">Forces</h4>
      <div className="scroll">
        <table className="lad">
          <thead>
            <tr>
              <th scope="col">unit</th>
              <th scope="col">of</th>
              <th scope="col">quality</th>
              <th scope="col" className="n">
                men
              </th>
              <th scope="col" className="n">
                strength
              </th>
              <th scope="col" className="n">
                morale
              </th>
            </tr>
          </thead>
          <tbody>
            {forces.map((row) => (
              <tr key={row.unit_id}>
                <td>
                  {row.name}
                  {row.posted_here && <span className="meta"> posted here</span>}
                </td>
                <td>{row.owner}</td>
                <td>{row.quality}</td>
                <td className="n">{row.men}</td>
                <td className="n">{row.strength}</td>
                <td className="n">{row.morale}</td>
              </tr>
            ))}
            {forces.length === 0 && (
              <tr>
                <td colSpan={6} className="meta">
                  none
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </>
  );
}

export function Openings({ openings }: { openings: AlmanachOpenings }) {
  return (
    <>
      <h4 className="sec">Openings</h4>
      <div className="row3">
        <div className="field">
          <span className="label">appable kin</span>
          <div className="val">
            {openings.appable.length === 0 && <span className="meta">none</span>}
            {openings.appable.map((p, i) => (
              <span key={p.id}>
                {i > 0 && ', '}
                <Link to={personUrl(p.id)}>{p.name}</Link>{' '}
                <span className="st">{tierMark(p.tier)}</span>
                <span className="gone"> {statusMark(p.status)}</span>
              </span>
            ))}
          </div>
        </div>
        <div className="field">
          <span className="label">household posts</span>
          <div className="val">
            {openings.posts.length === 0 && <span className="meta">none</span>}
            {openings.posts.map((p) => p.position).join(', ')}
          </div>
        </div>
        <div className="field">
          <span className="label">vacant seats</span>
          <div className="val">
            {openings.vacant_seats.length === 0 && <span className="meta">none</span>}
            {openings.vacant_seats.map((s, i) => (
              <span key={s.title_id}>
                {i > 0 && ', '}
                <Link to={`/staff/almanach/titles/${s.title_id}`}>{s.name || 'unnamed'}</Link>
              </span>
            ))}
          </div>
        </div>
      </div>
    </>
  );
}

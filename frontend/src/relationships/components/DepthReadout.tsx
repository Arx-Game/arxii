/**
 * The depth readout (#3957) — one number, and where it came from.
 *
 * Values only. A tie's depth is pooled from both sides, so the breakdown ends in one
 * line, Their Added Depth, rather than columns that would turn a relationship into a
 * scoreboard of who put in more. Affection and Conflict are on the breakdown only when
 * the payload carried them, which is the owner's own view.
 *
 * At the top tier there is no threshold to measure against, so the slash is dropped
 * entirely rather than printed against a dash.
 */

import { useId, useState } from 'react';

import { Eyebrow } from '@/character_sheets/components/sheet/primitives';
import type { Tie } from '../api';

export function DepthReadout({ tie }: { tie: Tie }) {
  const panelId = useId();
  const [open, setOpen] = useState(false);

  if (tie.depth == null || tie.breakdown == null) return null;
  const { breakdown } = tie;

  const face =
    tie.next_tier_threshold == null ? (
      `${tie.depth}`
    ) : (
      <>
        {tie.depth} <span className="refsheet-plate-soft">/ {tie.next_tier_threshold}</span>
      </>
    );

  const rows: Array<[string, number]> = [
    ['Tier', breakdown.tier],
    ['Scenes', breakdown.scenes],
    ['Invested', breakdown.invested],
    ['Their Added Depth', breakdown.their_added_depth],
  ];
  if (breakdown.affection != null) rows.push(['Affection', breakdown.affection]);
  if (breakdown.conflict != null) rows.push(['Conflict', breakdown.conflict]);

  return (
    <div className="refsheet-depth-slot">
      <Eyebrow>Depth</Eyebrow>
      <button
        type="button"
        className="refsheet-depth"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((was) => !was)}
      >
        {face}
      </button>
      <span className="refsheet-plate-soft">Tier {breakdown.tier}</span>
      {open && (
        <div className="refsheet-depth-pop" id={panelId}>
          <table>
            <tbody>
              {rows.map(([name, value]) => (
                <tr key={name}>
                  <td>{name}</td>
                  <td>{value}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

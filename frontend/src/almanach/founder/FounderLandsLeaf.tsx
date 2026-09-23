/**
 * FounderLandsLeaf (#3983 Plan B Task 6, plate F-IV "The Land") — the
 * baronies a claim on `draft.title_id` grants (`grantsOf`, `./steps`):
 * folded house line (seat/produces/sworn-to), the granted baronies as a
 * `.lad` table reusing `BaronyPage` for the disclosed row, then the claimed
 * rung's own section (prose, land shapes, a `.chain` breadcrumb to the
 * realm root).
 *
 * `BaronyPage` (`../document/BaronyPage`) keys its own `useDraft` prose
 * scratchpad by `barony.id` — a founder title id could collide with a
 * staff-mode Domain id (both are plain positive integers from the same
 * numeric space), so every `barony` this leaf builds negates the title id
 * (`id: -row.title_id`) before handing it to `BaronyPage`. `onSave` closes
 * over the real (positive) `title_id` directly, so the negation never
 * leaks into `setLand`.
 *
 * The plate's contents-rail "The Land" entry carries a nested `<ol>`
 * sub-list (Fervor/Arsura/Ascua/Undefined, `founder.html:f4`) live-breadcrumbing
 * the claimed chain while this chapter is open — omitted: the brief's own
 * Interfaces/Produces description covers only this leaf's own three
 * sections (row3/table/top-rung), never the contents rail, and
 * `FounderAlmanach.test.tsx`'s own contents-rail test asserts the "Land"
 * group's `<li>` list is exactly `['The Land', 'The Estate']` with no
 * nested content — adding it would need a second, deliberately-scoped
 * change to that shared rail this task's file list doesn't reach.
 *
 * The plate's own "on the Atlas" field is a decorative isle/pin diagram
 * (`.pin` with `.isle`/`.dot`/`.lbl` divs, hand-placed percentages) with no
 * backing coordinate data anywhere in `LadderRow`/`FounderDraft` — per the
 * ruling, this renders as a labeled dash ("set on review") rather than
 * fabricating a placement.
 */
import { Fragment, useState, type ReactNode } from 'react';

import { DRAFT_NOTE, STATES } from '../copy';
import { tierNoun } from '../ladder/tree';
import { useLandShapes } from '../queries';
import { BaronyPage } from '../document/BaronyPage';
import type { AlmanachBarony, LadderRow } from '../types';

import type { FounderDraft, UseFounderDraftResult } from './founderDraft';
import { grantsOf, landFactsOf } from './steps';

/** A rung reference cell (the "seat" field, the table's "in" column): no
 * row at all (a dash), a row with no authored name (the "Undefined" chip),
 * or the row's own name. Three distinct outputs, not collapsible into one
 * ternary — a plain `if` chain instead of nesting. */
function rungCell(row: LadderRow | null | undefined): ReactNode {
  if (!row) return <abbr title="none">—</abbr>;
  if (!row.is_defined) return <span className="chip undef">Undefined</span>;
  return row.name;
}

/** The rows from the realm root down to `row` (inclusive), walking
 * `parent_title_id` — the plate's `.chain` breadcrumb (kingdom › duchy › …
 * this rung). Root-first order. */
function chainToRoot(rows: LadderRow[], row: LadderRow): LadderRow[] {
  const chain: LadderRow[] = [row];
  let current = row;
  for (;;) {
    if (current.parent_title_id == null) break;
    const parent = rows.find((r) => r.title_id === current.parent_title_id);
    if (!parent) break;
    chain.unshift(parent);
    current = parent;
  }
  return chain;
}

export interface FounderLandsLeafProps {
  draft: FounderDraft;
  setLand: UseFounderDraftResult['setLand'];
  rows: LadderRow[];
  produces: string[];
  onNext: () => void;
}

export function FounderLandsLeaf({
  draft,
  setLand,
  rows,
  produces,
  onNext,
}: FounderLandsLeafProps) {
  const { data: landShapesPayload } = useLandShapes();
  const landShapes = landShapesPayload?.results ?? [];
  const [openTitleId, setOpenTitleId] = useState<number | null>(null);

  if (draft.title_id == null) return null;
  const facts = landFactsOf(rows, draft.title_id);
  if (!facts) return null;
  const { topRow, baronies, seatBarony } = facts;
  const chainIds = new Set(grantsOf(rows, draft.title_id).map((row) => row.title_id));

  const swornCounties = rows.filter(
    (row) =>
      (row.tier === 'county' || row.tier === 'march') &&
      row.parent_title_id === topRow.title_id &&
      row.state === STATES.unclaimed &&
      !chainIds.has(row.title_id)
  );

  const topLand = draft.lands[topRow.title_id];
  const openRow =
    openTitleId != null ? baronies.find((row) => row.title_id === openTitleId) : undefined;

  const toggleShape = (name: string) => {
    const current = topLand?.land_shape_names ?? [];
    setLand(topRow.title_id, {
      land_shape_names: current.includes(name)
        ? current.filter((n) => n !== name)
        : [...current, name],
    });
  };

  return (
    <main className="chapter">
      <h3>
        Lands of {draft.house_name}{' '}
        <span className="tier">
          {baronies.length} {tierNoun('barony', baronies.length)}
        </span>
      </h3>
      <div className="row3">
        <div className="field">
          <span className="label">seat</span>
          <div className="val">{rungCell(seatBarony)}</div>
        </div>
        <div className="field">
          <span className="label">produces</span>
          {produces.length > 0 ? (
            <div className="chips">
              {produces.map((name) => (
                <span className="chip" key={name}>
                  {name}
                </span>
              ))}
            </div>
          ) : (
            <div className="val">
              <abbr title="none">—</abbr>
            </div>
          )}
        </div>
        <div className="field">
          <span className="label">sworn to {topRow.name}</span>
          <div className="val">
            {swornCounties.length > 0 ? (
              swornCounties.map((row, index) => (
                <Fragment key={row.title_id}>
                  {index > 0 && ' · '}
                  {row.is_defined ? row.name : <span className="chip undef">Undefined</span>}
                </Fragment>
              ))
            ) : (
              <abbr title="none">—</abbr>
            )}
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
            </tr>
          </thead>
          <tbody>
            {baronies.map((row) => {
              const land = draft.lands[row.title_id];
              const expanded = openTitleId === row.title_id;
              const isSeat = row.title_id === seatBarony?.title_id;
              const parentRow = rows.find((r) => r.title_id === row.parent_title_id);
              const rowLabel = row.is_defined ? row.name : 'undefined barony';
              return (
                <tr key={row.title_id} className={expanded ? 'sel' : undefined}>
                  <td>
                    <button
                      type="button"
                      className="tg"
                      aria-expanded={expanded}
                      aria-label={`${expanded ? 'Collapse' : 'Expand'} ${rowLabel}`}
                      onClick={() => setOpenTitleId(expanded ? null : row.title_id)}
                    >
                      {expanded ? '▾' : '▸'}
                    </button>
                    {row.is_defined ? row.name : <span className="chip undef">Undefined</span>}
                    {isSeat && <span className="seat">seat of {draft.house_name}</span>}
                  </td>
                  <td>{rungCell(parentRow)}</td>
                  <td>
                    {land?.hall_name ? (
                      land.hall_name
                    ) : (
                      <span className="chip undef">Undefined</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {openRow &&
        (() => {
          const land = draft.lands[openRow.title_id];
          const parentRow = rows.find((r) => r.title_id === openRow.parent_title_id);
          const barony: AlmanachBarony = {
            id: -openRow.title_id,
            name: openRow.is_defined ? openRow.name : 'Undefined',
            in: parentRow?.name ?? '',
            hall: land?.hall_name ?? '',
            is_seat: openRow.title_id === seatBarony?.title_id,
            description: land?.description ?? '',
            land_shapes: land?.land_shape_names ?? [],
            population: 0,
          };
          return (
            <>
              {!openRow.is_defined && (
                <div className="field">
                  <input
                    type="text"
                    aria-label="Name the land"
                    value={land?.land_name ?? ''}
                    onChange={(event) =>
                      setLand(openRow.title_id, { land_name: event.target.value })
                    }
                  />
                </div>
              )}
              <BaronyPage barony={barony} onSave={(fields) => setLand(openRow.title_id, fields)} />
            </>
          );
        })()}
      <h4 className="sec">
        {topRow.name} <span className="tier">{tierNoun(topRow.tier, 1)}</span>
      </h4>
      <div className="chain">
        {chainToRoot(rows, topRow).map((row) => (
          <span key={row.title_id} className={row.title_id === topRow.title_id ? 'cur' : undefined}>
            <span className="tw">{tierNoun(row.tier, 1)}</span>
            {row.is_defined ? row.name : 'Undefined'}
          </span>
        ))}
      </div>
      <div className="field">
        <label htmlFor="founder-land-prose">the land, in your words</label>
        <textarea
          id="founder-land-prose"
          className="prose"
          value={topLand?.description ?? ''}
          onChange={(event) => setLand(topRow.title_id, { description: event.target.value })}
        />
      </div>
      <div className="field">
        <span className="label">land</span>
        <div className="chips" role="group" aria-label="Land shapes">
          {landShapes.map((shape) => {
            const pressed = (topLand?.land_shape_names ?? []).includes(shape.name);
            return (
              <button
                key={shape.id}
                type="button"
                className={pressed ? 'chip acc' : 'chip'}
                aria-pressed={pressed}
                onClick={() => toggleShape(shape.name)}
              >
                {shape.name}
              </button>
            );
          })}
        </div>
      </div>
      <div className="field">
        <span className="label">on the Atlas</span>
        <div className="val">
          <abbr title="none">—</abbr>
        </div>
      </div>
      <div className="savebar">
        <span className="note">{DRAFT_NOTE}</span>
        <button type="button" className="btn" onClick={onNext}>
          Next
        </button>
      </div>
    </main>
  );
}

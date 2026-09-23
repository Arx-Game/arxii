/**
 * LadderTable (#3983 Task 8, plate I `.lad`) — the realm ladder as a
 * disclosure tree: one row per `LadderRow`, nested by `parent_title_id`
 * (`buildLadderTree`, `./tree.ts`) and indented by tree depth (`.d1`/`.d2`/
 * `.d3`). A row's state chip renders BEFORE its holder name (`HeldByCell`),
 * an undefined rung's name renders as an `Undefined` chip instead of blank
 * text, a held barony that is another rung's seat gets a `seat of <house>`
 * marker, and a chain member (`comes_with !== ''`) gets a `comes with
 * <parent>` meta note — all per the plate's visual contract.
 *
 * Expansion is client-side only (#3983 Task 8 decision 3): a row's default
 * open/closed state comes from comparing its own tier to `pressedTier` (the
 * level bar's current pick — `defaultExpanded`, `./tree.ts`); a manual click
 * on a row's own disclosure button flips that default via `toggled`. `rows`
 * without children get a hidden spacer instead of a button (nothing to
 * disclose, matches `.tg.none` in the plate).
 *
 * A row's name is ALSO its own selection control (review fix round 1, #3983
 * Task 8): a `<button>` distinct from the disclosure toggle, so clicking it
 * calls `onSelectRow` and the caller can drive `selectedTitleId` (rendered
 * as the plate's `tr.sel` highlight) — the savebar's plant/batch actions use
 * whichever rung is selected as their `under` context.
 *
 * `trailingCell` (#3983 Plan B Task 4) lets a caller append one more column
 * without forking the table — the Founder Almanach's Seat picker (plates
 * F-I/F-I b) uses it for the per-row Claim button/`held`/`—` cell. Omitted,
 * the table renders exactly as it did before (Plan A's own tests rely on
 * this staying the default).
 */
import { useEffect, useId, useMemo, useState, type ReactNode } from 'react';

import { STATES } from '../copy';
import type { LadderRow } from '../types';
import { buildLadderTree, defaultExpanded, defaultPressedTier, type LadderTreeNode } from './tree';

export interface LadderTableProps {
  rows: LadderRow[];
  /** The level bar's current pick; defaults to the shallowest row tier when omitted. */
  pressedTier?: string | null;
  /** A rung to mark with the plate's `.sel` highlight (e.g. a freshly planted rung). */
  selectedTitleId?: number | null;
  /** Fires when a row's own name/title button is clicked (the plate's row-selection gesture). */
  onSelectRow?: (row: LadderRow) => void;
  /** An extra trailing column per row, rendered after `vassals` — see above. */
  trailingCell?: (row: LadderRow) => ReactNode;
}

function NumCell({ value }: { value: number }) {
  return <td className="n">{value > 0 ? value : <abbr title="none">—</abbr>}</td>;
}

function SwornToCell({ row }: { row: LadderRow }) {
  return <td>{row.sworn_to !== '' ? row.sworn_to : <abbr title="none">—</abbr>}</td>;
}

function HeldByCell({ row }: { row: LadderRow }) {
  if (row.state === STATES.unclaimed) {
    return (
      <td>
        <span className="chip open">{STATES.unclaimed}</span>
      </td>
    );
  }
  return <td className="held">{row.house_name}</td>;
}

interface NameCellProps {
  row: LadderRow;
  hasChildren: boolean;
  expanded: boolean;
  onToggle: () => void;
  onSelect: () => void;
}

function NameCell({ row, hasChildren, expanded, onToggle, onSelect }: NameCellProps) {
  const label = row.is_defined ? row.name : `undefined ${row.tier}`;
  return (
    <td>
      {hasChildren ? (
        <button
          type="button"
          className="tg"
          aria-expanded={expanded}
          aria-label={`${expanded ? 'Collapse' : 'Expand'} ${label}`}
          onClick={onToggle}
        >
          {expanded ? '▾' : '▸'}
        </button>
      ) : (
        <span className="tg none" aria-hidden="true">
          ▸
        </span>
      )}
      <span className="tw">{row.tier}</span>
      {row.is_defined ? (
        <button
          type="button"
          className="rung-name"
          aria-label={`Select ${label}`}
          onClick={onSelect}
        >
          {row.name}
        </button>
      ) : (
        <button
          type="button"
          className="chip undef"
          aria-label={`Select ${label}`}
          onClick={onSelect}
        >
          {STATES.undefined}
        </button>
      )}
      {row.tier === 'barony' && row.is_seat_of !== '' && (
        <span className="seat">seat of {row.is_seat_of}</span>
      )}
      {row.comes_with !== '' && <span className="meta">comes with {row.comes_with}</span>}
    </td>
  );
}

export function LadderTable({
  rows,
  pressedTier,
  selectedTitleId,
  onSelectRow,
  trailingCell,
}: LadderTableProps) {
  const tree = useMemo(() => buildLadderTree(rows), [rows]);
  const fallbackTier = useMemo(() => defaultPressedTier(rows), [rows]);
  const effectivePressedTier = pressedTier ?? fallbackTier;
  const [toggled, setToggled] = useState<Set<number>>(() => new Set());
  const demesneGlossId = useId();
  const vassalsGlossId = useId();

  // A fresh level-bar pick starts every rung back at its tier default — a
  // per-rung toggle from a previous pick shouldn't linger as a now-confusing
  // override under a different pressed tier.
  useEffect(() => {
    setToggled(new Set());
  }, [effectivePressedTier]);

  const toggle = (titleId: number) => {
    setToggled((prev) => {
      const next = new Set(prev);
      if (next.has(titleId)) {
        next.delete(titleId);
      } else {
        next.add(titleId);
      }
      return next;
    });
  };

  const isExpanded = (node: LadderTreeNode) => {
    const base = defaultExpanded(node.row.tier, effectivePressedTier);
    return toggled.has(node.row.title_id) ? !base : base;
  };

  const renderNodes = (nodes: LadderTreeNode[]): ReactNode[] => {
    const out: ReactNode[] = [];
    for (const node of nodes) {
      const hasChildren = node.children.length > 0;
      const expanded = isExpanded(node);
      const depthClass = `d${Math.min(node.depth + 1, 3)}`;
      const selected = selectedTitleId != null && node.row.title_id === selectedTitleId;
      out.push(
        <tr key={node.row.title_id} className={selected ? `${depthClass} sel` : depthClass}>
          <NameCell
            row={node.row}
            hasChildren={hasChildren}
            expanded={expanded}
            onToggle={() => toggle(node.row.title_id)}
            onSelect={() => onSelectRow?.(node.row)}
          />
          <HeldByCell row={node.row} />
          <SwornToCell row={node.row} />
          <NumCell value={node.row.demesne} />
          <NumCell value={node.row.vassals} />
          {trailingCell && <td>{trailingCell(node.row)}</td>}
        </tr>
      );
      if (hasChildren && expanded) {
        out.push(...renderNodes(node.children));
      }
    }
    return out;
  };

  return (
    <div className="scroll">
      <table className="lad">
        <thead>
          <tr>
            <th scope="col">title</th>
            <th scope="col">held by</th>
            <th scope="col">sworn to</th>
            <th scope="col" className="n">
              <button type="button" className="tip" aria-describedby={demesneGlossId}>
                demesne
                <span className="bub" id={demesneGlossId}>
                  baronies the holder keeps personally, wherever they lie
                </span>
              </button>
            </th>
            <th scope="col" className="n">
              <button type="button" className="tip" aria-describedby={vassalsGlossId}>
                vassals
                <span className="bub" id={vassalsGlossId}>
                  houses and unclaimed seats sworn beneath
                </span>
              </button>
            </th>
            {trailingCell && (
              <th scope="col">
                <span className="sr">claim</span>
              </th>
            )}
          </tr>
        </thead>
        <tbody>{renderNodes(tree)}</tbody>
      </table>
    </div>
  );
}

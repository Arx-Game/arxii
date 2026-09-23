/**
 * SeatPicker (#3983 Plan B Task 4, plates F-I/F-I b) — the founder's own
 * realm ladder: the same `LevelBar`/`LadderTable` Plan A's staff page uses
 * (`useLadder(realmId, 'founder')`, opened to any authenticated player by
 * Plan B Task 3), plus a trailing Claim column `LadderTable`'s new
 * `trailingCell` prop adds. A row claims when it's `claimable`, currently
 * `unclaimed`, and its tier ranks at or under the founder's Upbringing
 * ceiling (`permittedRank`, `./steps`); a held rung reads `held`, a rung
 * bundled into its parent's claim (`comes_with`) reads a dash — never a
 * button either way.
 *
 * The heading's "Change tier"/"Change realm" controls reuse the plate's own
 * `.switcher`/`.switcher-list` markup (`AlmanachPage.tsx`'s `RealmSwitcher`,
 * exported for this reuse) but NOT that component directly: its `onClick`
 * hard-navigates to `/staff/almanach/realms/:id`, a staff-only route a
 * founder can't reach — this file's own tiny switcher calls back into the
 * founder draft instead (`onSelectRealm`). See Task 4's report.
 */
import { useState, type ReactNode } from 'react';

import { CLAIM, REVIEW_NOTE, STATES } from '../copy';
import { LadderTable } from '../ladder/LadderTable';
import { LevelBar } from '../ladder/LevelBar';
import { defaultPressedTier, levelBarTiers, tierNoun } from '../ladder/tree';
import { useLadder, useRealms } from '../queries';
import type { LadderRow } from '../types';
import { TIER_RANK } from './steps';

export interface SeatPickerProps {
  realmId: number;
  /** The founder's Claim ceiling as a `TIER_RANK` number (`permittedRank`, `./steps`). */
  permittedRank: number;
  onSelectRealm: (realmId: number) => void;
  onClaim: (row: LadderRow) => void;
}

function capitalize(word: string): string {
  return word.length === 0 ? word : word[0].toUpperCase() + word.slice(1);
}

/** `unclaimed_by_tier[tier]`, folding march into county — mirrors
 * `LevelBar`'s own (unexported) `tierCount`. */
function tierCount(unclaimedByTier: Record<string, number>, tier: string): number {
  const base = unclaimedByTier[tier] ?? 0;
  return tier === 'county' ? base + (unclaimedByTier.march ?? 0) : base;
}

function trailingCell(
  row: LadderRow,
  permitted: number,
  onClaim: (row: LadderRow) => void
): ReactNode {
  const rank = TIER_RANK[row.tier] ?? 0;
  if (row.claimable && row.state === STATES.unclaimed && rank <= permitted) {
    const label = row.is_defined ? `${CLAIM} ${row.name}` : CLAIM;
    return (
      <button type="button" className="btn quiet sm" onClick={() => onClaim(row)}>
        {label}
      </button>
    );
  }
  if (row.comes_with !== '') {
    return <abbr title="none">—</abbr>;
  }
  if (row.state !== STATES.unclaimed) {
    return <span className="meta">{STATES.held.toLowerCase()}</span>;
  }
  return null;
}

export function SeatPicker({ realmId, permittedRank, onSelectRealm, onClaim }: SeatPickerProps) {
  const { data: realmsPayload } = useRealms();
  const realms = realmsPayload?.results ?? [];
  const realm = realms.find((r) => r.id === realmId);
  const { data: payload } = useLadder(realmId, 'founder');
  const rows = payload?.rows ?? [];
  const unclaimedByTier = payload?.unclaimed_by_tier ?? {};
  const fallbackTier = defaultPressedTier(rows);
  const [pressedTier, setPressedTier] = useState<string | null>(null);
  const effectivePressedTier = pressedTier ?? fallbackTier;

  const [tierOpen, setTierOpen] = useState(false);
  const [realmOpen, setRealmOpen] = useState(false);

  const tiers = levelBarTiers(rows);

  // Plate F-I's tier span reads "vassal of House Piropa" — whoever the
  // ladder's own root rows are sworn to, crown-suffix stripped (mirrors
  // `AlmanachPage.tsx`'s `crownHolder`).
  const liegeName =
    rows
      .map((row) => row.sworn_to)
      .find((swornTo) => swornTo.endsWith(' (crown)'))
      ?.replace(/ \(crown\)$/, '') ??
    rows.find((row) => row.parent_title_id == null)?.sworn_to ??
    '';

  if (!payload) {
    return <p className="meta">Loading the ladder…</p>;
  }

  return (
    <>
      <h3>
        <span className="switcher">
          <button
            type="button"
            className="lnk plain"
            aria-label="Change tier"
            aria-haspopup="listbox"
            aria-expanded={tierOpen}
            onClick={() => setTierOpen((open) => !open)}
          >
            {effectivePressedTier ? capitalize(tierNoun(effectivePressedTier, 2)) : ''}
          </button>
          {tierOpen && (
            <ul className="switcher-list" role="listbox" aria-label="Tiers">
              {tiers.map((tier) => (
                <li key={tier} role="option" aria-selected={tier === effectivePressedTier}>
                  <button
                    type="button"
                    onClick={() => {
                      setPressedTier(tier);
                      setTierOpen(false);
                    }}
                  >
                    {capitalize(tierNoun(tier, 2))} · {tierCount(unclaimedByTier, tier)}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </span>{' '}
        of{' '}
        <span className="switcher">
          <button
            type="button"
            className="lnk"
            aria-label="Change realm"
            aria-haspopup="listbox"
            aria-expanded={realmOpen}
            onClick={() => setRealmOpen((open) => !open)}
          >
            {realm?.name ?? `Realm ${realmId}`}
          </button>
          {realmOpen && (
            <ul className="switcher-list" role="listbox" aria-label="Realms">
              {realms.map((r) => (
                <li key={r.id} role="option" aria-selected={r.id === realmId}>
                  <button
                    type="button"
                    onClick={() => {
                      setRealmOpen(false);
                      onSelectRealm(r.id);
                    }}
                  >
                    {r.name}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </span>
        {liegeName !== '' && <span className="tier">vassal of House {liegeName}</span>}
      </h3>
      <LevelBar
        rows={rows}
        unclaimedByTier={unclaimedByTier}
        pressedTier={effectivePressedTier}
        onPressTier={setPressedTier}
      />
      <LadderTable
        rows={rows}
        pressedTier={effectivePressedTier}
        trailingCell={(row) => trailingCell(row, permittedRank, onClaim)}
      />
      <div className="savebar">
        <span className="note">{REVIEW_NOTE}</span>
      </div>
    </>
  );
}

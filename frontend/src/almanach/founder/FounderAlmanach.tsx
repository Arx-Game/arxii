/**
 * FounderAlmanach (#3983 Plan B Task 4) — the founder's own Almanach de
 * Catenys, mounted inside character creation's Lineage stage
 * (`FamilyPathSection`) in place of the old `HouseFoundingPanel` (#1884
 * Phase D). Shares the staff Almanach's `.almanach` chassis (plates F-I
 * onward mirror plates S-I/S-II's three-column grid) but every read here is
 * founder-scoped (`useLadder(realmId, 'founder')`, the realms/charter/
 * land-shapes routes Plan B Task 3 opens to any authenticated player) and
 * every write stays in the browser (`useFounderDraft`) until the review
 * step (Task 6) files the nested claim (Task 3's `POST .../house-claim/`).
 *
 * Tasks 5-6 build the House/Family/Land/Estate chapters and the submitted-
 * claim view on top of this shell; until then, a step past the Seat shows a
 * plain placeholder next to `RecordSoFar`, and a filed claim shows a
 * minimal status line rather than the full submitted-claim plate.
 */
import { useState } from 'react';

import { useClaimableTitles, useHouseClaim } from '@/character-creation/queries';
import type { CharacterDraft } from '@/character-creation/types';

import '../almanach.css';
import { FOUNDER_CRUMB, STATES } from '../copy';
import { defaultPressedTier, TIER_LABELS } from '../ladder/tree';
import { useCharter, useLadder, useRealms } from '../queries';
import type { LadderRow } from '../types';

import { useFounderDraft } from './founderDraft';
import { RecordSoFar } from './RecordSoFar';
import { SeatPicker } from './SeatPicker';
import { FOUNDER_CONTENTS, permittedRank, type FounderStep } from './steps';

const STEP_LABELS: Record<FounderStep, string> = {
  seat: 'The Seat',
  house: 'The House',
  family: 'The Family',
  land: 'The Land',
  estate: 'The Estate',
  record: 'The Record',
};

/** "N ducal/county/barony seats unclaimed" (plates F-I/F-I b's `vassals` dd)
 * — `unclaimed_by_tier[tier]`, folding march into county like `LevelBar`. */
function seatsUnclaimed(unclaimedByTier: Record<string, number>, tier: string): string {
  const base = unclaimedByTier[tier] ?? 0;
  const count = tier === 'county' ? base + (unclaimedByTier.march ?? 0) : base;
  const label = (TIER_LABELS[tier] ?? tier).toLowerCase();
  return `${count} ${label} seats unclaimed`;
}

/** The realm's crown-holding house name, crown-suffix stripped — mirrors
 * `AlmanachPage.tsx`'s own `crownHolder` convention (a root row's
 * `sworn_to` ends " (crown)" when it's sworn straight to the realm's own
 * crown house). Falls back to any root row's raw `sworn_to` when no row
 * carries that suffix. */
function crownName(rows: LadderRow[]): string {
  return (
    rows
      .map((row) => row.sworn_to)
      .find((swornTo) => swornTo.endsWith(' (crown)'))
      ?.replace(/ \(crown\)$/, '') ??
    rows.find((row) => row.parent_title_id == null)?.sworn_to ??
    ''
  );
}

/** Every rung `houseName` holds, by name, joined "Fervor · Arsura" (plate
 * F-I b's `holds` dd) — every row whose own `house_name` matches. */
function holdingsOf(rows: LadderRow[], houseName: string): string {
  return rows
    .filter((row) => row.house_name === houseName)
    .map((row) => row.name)
    .join(' · ');
}

/** "N county seats unclaimed" among `parentTitleId`'s own direct children
 * (plate F-I b's immediate-liege `vassals` dd) — unlike `seatsUnclaimed`
 * (a realm-wide `unclaimed_by_tier` count), this counts straight off the
 * live `rows`, scoped to one rung's own children. */
function childSeatsUnclaimed(rows: LadderRow[], parentTitleId: number): string {
  const children = rows.filter((row) => row.parent_title_id === parentTitleId);
  const unclaimed = children.filter((row) => row.state === STATES.unclaimed).length;
  const tier = children[0]?.tier ?? '';
  const label = (TIER_LABELS[tier] ?? tier).toLowerCase();
  return `${unclaimed} ${label} seats unclaimed`;
}

/**
 * The Seat step's right rail (plate F-I/F-I b, before `RecordSoFar` takes
 * over from plate F-II on): the selected rung's immediate liege (when its
 * parent title is already held — plate F-I b's "House Candela" group) plus
 * the realm's crown house (plate F-I's only group, or F-I b's second one),
 * and the realm's charter. Simplified from the plate — see Task 4's report
 * for the fields the ladder/charter reads don't carry (a house's own
 * Quiddity, named peer vassals) and are left out rather than invented.
 */
function LiegeRealmAside({
  realmId,
  rows,
  unclaimedByTier,
  selectedRow,
}: {
  realmId: number;
  rows: LadderRow[];
  unclaimedByTier: Record<string, number>;
  selectedRow: LadderRow | null;
}) {
  const { data: realmsPayload } = useRealms();
  const realm = realmsPayload?.results.find((r) => r.id === realmId);
  const { data: charter } = useCharter(realmId);
  const tier = defaultPressedTier(rows);
  const liegeName = crownName(rows);

  // The selected rung's own liege, when it's a claimed rung's own vassal
  // (its parent title is held by a house) — plate F-I b: selecting
  // Solfatara (sworn to Fervor, now held by Candela) shows "House Candela"
  // ahead of the realm-crown group. A root row (no parent) or a still-
  // unclaimed parent has no immediate liege of its own to show, matching
  // plate F-I's single-group shape.
  const parentRow =
    selectedRow?.parent_title_id != null
      ? rows.find((row) => row.title_id === selectedRow.parent_title_id)
      : undefined;
  const immediateLiege =
    parentRow && parentRow.state !== STATES.unclaimed && parentRow.house_name !== ''
      ? parentRow
      : undefined;

  return (
    <aside className="record">
      {immediateLiege && (
        <>
          <h4>House {immediateLiege.house_name}</h4>
          <dl>
            <dt>holds</dt>
            <dd>{holdingsOf(rows, immediateLiege.house_name)}</dd>
            <dt>vassals</dt>
            <dd>{childSeatsUnclaimed(rows, immediateLiege.title_id)}</dd>
          </dl>
        </>
      )}
      {liegeName !== '' && (
        <>
          <h4>House {liegeName}</h4>
          <dl>
            <dt>crown</dt>
            <dd>{realm?.formal_name ? realm.formal_name : <abbr title="none">—</abbr>}</dd>
            <dt>vassals</dt>
            <dd>{tier ? seatsUnclaimed(unclaimedByTier, tier) : <abbr title="none">—</abbr>}</dd>
          </dl>
        </>
      )}
      <h4>{realm?.name ?? `Realm ${realmId}`}</h4>
      <dl>
        <dt>succession</dt>
        <dd>
          {charter?.succession_law ? (
            <>
              {charter.succession_law.name}
              {charter.succession_law.codex_entry_id != null && (
                <>
                  {' · '}
                  <a href={`/codex/${charter.succession_law.codex_entry_id}`}>codex</a>
                </>
              )}
            </>
          ) : (
            <abbr title="none">—</abbr>
          )}
        </dd>
        <dt>particle</dt>
        <dd>
          {charter ? (
            `${charter.particle.born} · ${charter.particle.taken_in}`
          ) : (
            <abbr title="none">—</abbr>
          )}
        </dd>
      </dl>
    </aside>
  );
}

export function FounderAlmanach({ draft }: { draft: CharacterDraft }) {
  const { data: claim } = useHouseClaim(draft.id);
  const { data: realmsPayload } = useRealms();
  const realms = realmsPayload?.results ?? [];
  const { data: titles = [] } = useClaimableTitles();
  const { draft: fd, set } = useFounderDraft(draft.id);

  const effectiveRealmId = fd.realm_id ?? draft.selected_area?.realm_id ?? realms[0]?.id ?? null;
  const [step, setStep] = useState<FounderStep>(fd.title_id != null ? 'house' : 'seat');

  const { data: ladderPayload } = useLadder(effectiveRealmId, 'founder');
  const rows = ladderPayload?.rows ?? [];
  const unclaimedByTier = ladderPayload?.unclaimed_by_tier ?? {};

  const rank = permittedRank(draft.selected_origin_template?.max_claim_tier);
  const seatRow =
    fd.title_id != null ? rows.find((row) => row.title_id === fd.title_id) : undefined;

  // The Seat step's own row selection (fix round 1, Finding 2): defaults to
  // the shallowest root row (matches plate F-I's own `.sel` on Fervor, and
  // `AlmanachPage.tsx`'s `RealmLadderPage` fallback convention) until the
  // founder picks or claims a different rung.
  const [selectedTitleId, setSelectedTitleId] = useState<number | null>(null);
  const selectedRow =
    (selectedTitleId != null ? rows.find((row) => row.title_id === selectedTitleId) : undefined) ??
    rows.find((row) => row.parent_title_id == null) ??
    null;

  const handleSelectRealm = (id: number) => {
    set('realm_id', id);
  };

  const handleSelectRow = (row: LadderRow) => {
    setSelectedTitleId(row.title_id);
  };

  const handleClaim = (row: LadderRow) => {
    const title = titles.find((t) => t.id === row.title_id);
    const templateId = title?.templates[0]?.id ?? null;
    set('title_id', row.title_id);
    set('realm_id', effectiveRealmId);
    set('template_id', templateId);
    setSelectedTitleId(row.title_id);
    setStep('house');
  };

  if (claim) {
    // Task B6 replaces this with the full submitted-claim plate.
    return (
      <div className="almanach">
        <div className="bar">
          <span className="crumb">
            {FOUNDER_CRUMB.map((crumb) => (
              <span key={crumb}>{crumb}</span>
            ))}
          </span>
          <span className="right">
            <span className="mode">founder</span>
          </span>
        </div>
        <p className="meta">
          House {claim.house_name}: {claim.title_name} ({claim.status})
        </p>
      </div>
    );
  }

  if (effectiveRealmId == null) {
    return <div className="almanach" />;
  }

  return (
    <div className="almanach">
      <div className="bar">
        <span className="crumb">
          {FOUNDER_CRUMB.map((crumb) => (
            <span key={crumb}>{crumb}</span>
          ))}
        </span>
        <span className="right">
          <span className="mode">founder</span>
        </span>
      </div>
      <div className="almanac">
        <aside className="contents">
          {FOUNDER_CONTENTS.map((group, index) => (
            // "Holdings" repeats as a group label (two distinct `.mv` blocks per
            // the plate); index disambiguates the key since the list is static.
            <div className="mv" key={`${group.label}-${index}`}>
              <span className="label">{group.label}</span>
              <ol>
                {group.entries.map((entry) => {
                  const reachable = entry.step === 'seat' || fd.title_id != null;
                  let className: string | undefined;
                  if (entry.step === step) {
                    className = 'cur';
                  } else if (!reachable) {
                    className = 'ro';
                  }
                  return (
                    <li key={entry.step} className={className}>
                      {entry.label}
                    </li>
                  );
                })}
              </ol>
            </div>
          ))}
        </aside>
        <main className="chapter">
          {step === 'seat' ? (
            <SeatPicker
              realmId={effectiveRealmId}
              permittedRank={rank}
              selectedTitleId={selectedRow?.title_id ?? null}
              onSelectRow={handleSelectRow}
              onSelectRealm={handleSelectRealm}
              onClaim={handleClaim}
            />
          ) : (
            <>
              <h3>{STEP_LABELS[step]}</h3>
              <p className="meta">Coming soon.</p>
            </>
          )}
        </main>
        {step === 'seat' ? (
          <LiegeRealmAside
            realmId={effectiveRealmId}
            rows={rows}
            unclaimedByTier={unclaimedByTier}
            selectedRow={selectedRow}
          />
        ) : (
          <RecordSoFar
            draft={fd}
            seatName={seatRow?.name ?? ''}
            swornTo={seatRow?.sworn_to ?? ''}
          />
        )}
      </div>
    </div>
  );
}

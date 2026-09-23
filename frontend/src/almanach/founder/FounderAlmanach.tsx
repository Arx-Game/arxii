/**
 * FounderAlmanach (#3983 Plan B Task 4-6) — the founder's own Almanach de
 * Catenys, mounted inside character creation's Lineage stage
 * (`FamilyPathSection`) in place of the old `HouseFoundingPanel` (#1884
 * Phase D, retired outright by Task 6). Shares the staff Almanach's
 * `.almanach` chassis (plates F-I onward mirror plates S-I/S-II's
 * three-column grid) but every read here is founder-scoped
 * (`useLadder(realmId, 'founder')`, the realms/charter/land-shapes routes
 * Plan B Task 3 opens to any authenticated player) and every write stays in
 * the browser (`useFounderDraft`) until the Record step files the nested
 * claim (Task 3's `POST .../house-claim/`).
 *
 * `SeatPicker`, the `document/FamilyChapter` `FounderFamilyChapter` mounts,
 * and every Task 6 chapter (`FounderLandsLeaf`/`FounderEstateLeaf`/
 * `FounderRecord`) each render their own `<main className="chapter">` —
 * `FounderHouseChapter` set that precedent (Task 5); this shell's own
 * `<main>` wrapper is used ONLY for `SeatPicker` (which does not self-wrap)
 * and the "resolving the template" fallback, never doubled up around a
 * chapter that already provides one.
 */
import { useState, type ReactNode } from 'react';

import { useClaimableTitles, useHouseClaim } from '@/character-creation/queries';
import type { HouseClaimStatus, HouseTemplateOption } from '@/character-creation/api';
import type { CharacterDraft } from '@/character-creation/types';

import '../almanach.css';
import { FOUNDER_CRUMB, STATES } from '../copy';
import {
  crownOrRootSwornTo,
  defaultPressedTier,
  TIER_LABELS,
  unclaimedForTier,
} from '../ladder/tree';
import { useCharter, useLadder, useRealms } from '../queries';
import type { LadderRow } from '../types';

import { useFounderDraft } from './founderDraft';
import { FounderEstateLeaf } from './FounderEstateLeaf';
import { FounderFamilyChapter } from './FounderFamilyChapter';
import { FounderHouseChapter } from './FounderHouseChapter';
import { FounderLandsLeaf } from './FounderLandsLeaf';
import { FounderRecord } from './FounderRecord';
import { RecordSoFar } from './RecordSoFar';
import { SeatPicker } from './SeatPicker';
import { SubmittedPlate } from './SubmittedPlate';
import {
  FOUNDER_CONTENTS,
  grantsOf,
  landBaseLine,
  landFactsOf,
  permittedRank,
  type FounderStep,
} from './steps';

/** No name field reaches these founder components yet (`CharacterDraft`
 * carries none) — every chapter that needs the founder's own display name
 * uses this same literal, matching `FounderHouseChapter`'s own disclosed
 * gap (see its doc comment and the Task 5 report). */
const YOU_NAME = 'Given name';

const STEP_ORDER: FounderStep[] = ['seat', 'house', 'family', 'land', 'estate', 'record'];

/** Whether `step` is at or past `target` in the founder's fixed chapter
 * order — the record rail's own step-gated rows (quiddity/you/the land/the
 * estate only appear once their chapter is reached, plates F-II/F-III's
 * `.todo` rows becoming real entries chapter by chapter). */
function atOrPast(step: FounderStep, target: FounderStep): boolean {
  return STEP_ORDER.indexOf(step) >= STEP_ORDER.indexOf(target);
}

/** "N ducal/county/barony seats unclaimed" (plates F-I/F-I b's `vassals` dd)
 * — `unclaimedForTier` (`../ladder/tree`) for the fold, this file's own
 * label formatting on top. */
function seatsUnclaimed(unclaimedByTier: Record<string, number>, tier: string): string {
  const count = unclaimedForTier(unclaimedByTier, tier);
  const label = (TIER_LABELS[tier] ?? tier).toLowerCase();
  return `${count} ${label} seats unclaimed`;
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

/** "the estate" record line (`<name> · <capital>`), or `''` before the
 * founder has named an estate — no capital name known yet reads as the
 * bare estate name rather than a trailing " · ". */
function estateLineOf(estateName: string, capitalName: string | undefined): string {
  if (estateName === '') return '';
  if (capitalName) return `${estateName} · ${capitalName}`;
  return estateName;
}

/** The picked template's first aspect definition's chosen option name(s)
 * (plate F-II's "quiddity" row, plate F-VI's `.row3` "quiddity" field) —
 * `''` before a template/pick exist. */
function quiddityNameOf(
  template: HouseTemplateOption | undefined,
  picks: Record<number, number[]>
): string {
  const quiddity = template?.aspect_definitions[0];
  if (!quiddity) return '';
  const pickedIds = picks[quiddity.id] ?? [];
  return quiddity.options
    .filter((option) => pickedIds.includes(option.id))
    .map((option) => option.name)
    .join(' · ');
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
  const liegeName = crownOrRootSwornTo(rows);

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
  const {
    draft: fd,
    set,
    addKin,
    updateKin,
    removeKin,
    setLand,
    reset,
  } = useFounderDraft(draft.id);

  const effectiveRealmId = fd.realm_id ?? draft.selected_area?.realm_id ?? realms[0]?.id ?? null;
  const [step, setStep] = useState<FounderStep>(fd.title_id != null ? 'house' : 'seat');
  const [justSubmitted, setJustSubmitted] = useState<HouseClaimStatus | null>(null);
  // Which barony's own page `FounderLandsLeaf` has disclosed — lifted up
  // here (rather than kept as that leaf's own internal state) so the
  // contents rail's nested chain sub-list (below) can open one from
  // outside the leaf, not just from the leaf's own table-row toggle.
  const [openBaronyId, setOpenBaronyId] = useState<number | null>(null);

  const { data: ladderPayload } = useLadder(effectiveRealmId, 'founder');
  const rows = ladderPayload?.rows ?? [];
  const unclaimedByTier = ladderPayload?.unclaimed_by_tier ?? {};
  const { data: charter } = useCharter(effectiveRealmId);

  const rank = permittedRank(draft.selected_origin_template?.max_claim_tier);
  const seatRow =
    fd.title_id != null ? rows.find((row) => row.title_id === fd.title_id) : undefined;

  const title = titles.find((t) => t.id === fd.title_id);
  // `fd.template_id` can be persisted `null` (M8, final review) when
  // `handleClaim` ran before `useClaimableTitles()` resolved — falling back
  // to the title's own first template keeps that draft usable instead of
  // showing "Loading…" on every later visit forever.
  const template =
    fd.template_id != null
      ? title?.templates.find((t) => t.id === fd.template_id)
      : title?.templates[0];
  const quiddityName = quiddityNameOf(template, fd.aspect_picks);
  const features = (template?.features ?? []).map((feature) => ({
    name: feature.name,
    // `HouseFeature` (`src/generated/api.d.ts`) carries no codex link field
    // — every entry is real (the name is authored content), just never
    // linked, the same honest-gap call `BaronyPage`'s own produces ledger
    // makes rather than fabricating an id.
    codexEntryId: null,
  }));
  const produces = template?.holdings.map((holding) => holding.name) ?? [];

  const landFacts = fd.title_id != null ? landFactsOf(rows, fd.title_id) : null;
  const landLineShort = landFacts ? landBaseLine(landFacts, fd.lands) : '';
  const landLineFull = landFacts
    ? `${landLineShort} · ${
        (fd.lands[landFacts.topRow.title_id]?.land_shape_names ?? []).join(', ') || 'Undefined'
      } · ${produces.join(', ') || 'Undefined'}`
    : '';
  const estateLine = estateLineOf(fd.estate_name, charter?.capital_name);

  // The contents rail's "The Land" entry nests the claimed chain plus its
  // loose extras (plate F-IV's own `.contents` sub-list, `founder.html:f4`)
  // — `grantsOf` already returns chain-first-then-extras, the exact order
  // the plate shows. Empty (and so hidden) until a seat is picked.
  const landGrants = fd.title_id != null ? grantsOf(rows, fd.title_id) : [];
  const landOpenTargetId = openBaronyId ?? fd.title_id;

  const handleOpenLandRung = (row: LadderRow) => {
    setStep('land');
    setOpenBaronyId(row.tier === 'barony' ? row.title_id : null);
  };

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
    const claimedTitle = titles.find((t) => t.id === row.title_id);
    const templateId = claimedTitle?.templates[0]?.id ?? null;
    set('title_id', row.title_id);
    set('realm_id', effectiveRealmId);
    set('template_id', templateId);
    setSelectedTitleId(row.title_id);
    setStep('house');
  };

  const submittedClaim = claim ?? justSubmitted;
  if (submittedClaim) {
    return (
      <div className="almanach">
        <SubmittedPlate
          houseName={submittedClaim.house_name}
          status={submittedClaim.status ?? 'pending'}
          reviewNote={submittedClaim.review_note}
        />
      </div>
    );
  }

  if (effectiveRealmId == null) {
    return <div className="almanach" />;
  }

  let chapter: ReactNode;
  if (step === 'seat') {
    chapter = (
      <main className="chapter">
        <SeatPicker
          realmId={effectiveRealmId}
          permittedRank={rank}
          selectedTitleId={selectedRow?.title_id ?? null}
          onSelectRow={handleSelectRow}
          onSelectRealm={handleSelectRealm}
          onClaim={handleClaim}
        />
      </main>
    );
  } else if (!template) {
    // The claimed title/template are still resolving (`useClaimableTitles`
    // hasn't returned yet, or the claim was made before it loaded) — every
    // chapter past the Seat requires a real template, so this is a brief
    // loading gap, never a stuck state once the query settles.
    chapter = (
      <main className="chapter">
        <p className="meta">Loading…</p>
      </main>
    );
  } else if (step === 'house') {
    chapter = (
      <FounderHouseChapter
        draft={fd}
        set={set}
        template={template}
        seatName={seatRow?.name ?? ''}
        seatTier={seatRow?.tier ?? ''}
        realmId={effectiveRealmId}
        youName={YOU_NAME}
        onNext={() => setStep('family')}
      />
    );
  } else if (step === 'family') {
    chapter = (
      <FounderFamilyChapter
        draft={fd}
        set={set}
        addKin={addKin}
        updateKin={updateKin}
        removeKin={removeKin}
        template={template}
        youName={YOU_NAME}
        onNext={() => setStep('land')}
      />
    );
  } else if (step === 'land') {
    chapter = (
      <FounderLandsLeaf
        draft={fd}
        setLand={setLand}
        rows={rows}
        produces={produces}
        openTitleId={openBaronyId}
        onOpenTitleId={setOpenBaronyId}
        onNext={() => setStep('estate')}
      />
    );
  } else if (step === 'estate') {
    chapter = (
      <FounderEstateLeaf
        draft={fd}
        set={set}
        realmId={effectiveRealmId}
        onNext={() => setStep('record')}
      />
    );
  } else {
    chapter = (
      <FounderRecord
        draft={fd}
        characterDraftId={draft.id}
        template={template}
        quiddityName={quiddityName}
        seatName={seatRow?.name ?? ''}
        seatTier={seatRow?.tier ?? ''}
        swornTo={seatRow?.sworn_to ?? ''}
        landLine={landLineFull}
        estateLine={estateLine}
        realmId={effectiveRealmId}
        youName={YOU_NAME}
        reset={reset}
        onBack={() => setStep('estate')}
        onSubmitted={(result) => setJustSubmitted(result)}
      />
    );
  }

  // The Seat step keeps its own liege/realm rail; the Record step drops the
  // third column entirely (plate F-VI's own 2-column `.almanac` grid,
  // reflected in the `gridTemplateColumns` override above); every other
  // step shows the running `RecordSoFar` summary.
  let aside: ReactNode = null;
  if (step === 'seat') {
    aside = (
      <LiegeRealmAside
        realmId={effectiveRealmId}
        rows={rows}
        unclaimedByTier={unclaimedByTier}
        selectedRow={selectedRow}
      />
    );
  } else if (step !== 'record') {
    aside = (
      <RecordSoFar
        draft={fd}
        seatName={seatRow?.name ?? ''}
        swornTo={seatRow?.sworn_to ?? ''}
        step={step}
        quiddityName={quiddityName !== '' ? quiddityName : undefined}
        features={features.length > 0 ? features : undefined}
        youName={atOrPast(step, 'family') ? YOU_NAME : undefined}
        landText={atOrPast(step, 'land') ? landLineShort : undefined}
        estateText={atOrPast(step, 'estate') ? estateLine : undefined}
      />
    );
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
      <div
        className="almanac"
        style={step === 'record' ? { gridTemplateColumns: '13rem minmax(0,1fr)' } : undefined}
      >
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
                      {entry.step === 'land' && landGrants.length > 0 && (
                        <ol>
                          {landGrants.map((row) => {
                            const isCur = step === 'land' && row.title_id === landOpenTargetId;
                            return (
                              <li key={row.title_id} className={isCur ? 'cur' : undefined}>
                                <button type="button" onClick={() => handleOpenLandRung(row)}>
                                  {row.is_defined ? (
                                    row.name
                                  ) : (
                                    <span className="chip undef">Undefined</span>
                                  )}
                                </button>
                              </li>
                            );
                          })}
                        </ol>
                      )}
                    </li>
                  );
                })}
              </ol>
            </div>
          ))}
        </aside>
        {chapter}
        {aside}
      </div>
    </div>
  );
}

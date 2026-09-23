/**
 * AlmanachPage (#3983 Tasks 8-9) — the Almanach de Catenys staff
 * house-builder's route element for all three `/staff/almanach*` routes
 * (`App.tsx`). With no `:realmId`/`:houseId` it redirects to the first realm
 * (or shows a bare realm list when there are none yet, #3983 Task 8 decision
 * 4); `:houseId` renders Task 9's `HouseDocument` (plates S-III to S-VIII);
 * `:realmId` renders the realm ladder —
 * plates S-I/S-II's visual contract: the three-column `.almanac` grid
 * (contents rail | chapter | record rail), the realm name as a switcher
 * `<button>`, the `.lvl` level bar, the `.lad` disclosure table, and a save
 * bar dispatching `almanach_plant_rung`/`almanach_batch_unclaimed`.
 *
 * The record rail's "on record" `<dl>` leads with `crown` (derived from a
 * row's own " (crown)"-suffixed `sworn_to`, review fix round 1) plus
 * `default tithe` (`AlmanachRealm.default_tithe_pct`) — the plate's other
 * charter fields (succession law, particle, quiddities) need realm/house
 * data no Task 7 API exposes yet, so they stay for a future Charter page
 * rather than being invented here.
 */
import { useEffect, useMemo, useState } from 'react';
import { Link, Navigate, useNavigate, useParams } from 'react-router-dom';

import { useAlmanachMutation, useHouses, useLadder, useRealms } from './queries';
import { buildLadderTree, defaultPressedTier } from './ladder/tree';
import { LevelBar } from './ladder/LevelBar';
import { LadderTable } from './ladder/LadderTable';
import { PlantRungDialog } from './ladder/PlantRungDialog';
import { BatchUnclaimedDialog } from './ladder/BatchUnclaimedDialog';
import { HouseDocument } from './document/HouseDocument';
import type { AlmanachRealm } from './types';
import './almanach.css';

function RealmSwitcher({
  realm,
  realms,
  realmId,
}: {
  realm?: AlmanachRealm;
  realms: AlmanachRealm[];
  realmId: number;
}) {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);

  return (
    <span className="switcher">
      <button
        type="button"
        className="lnk"
        aria-label="Change realm"
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        {realm?.name ?? `Realm ${realmId}`}
      </button>
      {open && (
        <ul className="switcher-list" role="listbox" aria-label="Realms">
          {realms.map((r) => (
            <li key={r.id} role="option" aria-selected={r.id === realmId}>
              <button
                type="button"
                onClick={() => {
                  setOpen(false);
                  navigate(`/staff/almanach/realms/${r.id}`);
                }}
              >
                {r.name}
              </button>
            </li>
          ))}
        </ul>
      )}
    </span>
  );
}

function RealmLadderPage({ realmId, realms }: { realmId: number; realms: AlmanachRealm[] }) {
  const realm = realms.find((r) => r.id === realmId);
  const { data: payload } = useLadder(realmId, 'staff');
  const { data: housesPayload } = useHouses(realmId);
  const rows = useMemo(() => payload?.rows ?? [], [payload]);
  const unclaimedByTier = payload?.unclaimed_by_tier ?? {};
  const tree = useMemo(() => buildLadderTree(rows), [rows]);
  const fallbackTier = useMemo(() => defaultPressedTier(rows), [rows]);

  const [pressedTier, setPressedTier] = useState<string | null>(null);
  useEffect(() => {
    setPressedTier(fallbackTier);
  }, [realmId, fallbackTier]);
  const effectivePressedTier = pressedTier ?? fallbackTier;

  const [plantOpen, setPlantOpen] = useState(false);
  const [batchOpen, setBatchOpen] = useState(false);
  const [selectedTitleId, setSelectedTitleId] = useState<number | null>(null);

  const plantMutation = useAlmanachMutation('almanach_plant_rung');
  const batchMutation = useAlmanachMutation('almanach_batch_unclaimed');

  const houses = housesPayload?.results ?? [];
  // The savebar's plant/batch "under" context (review fix round 1, #3983
  // Task 8): whichever rung the staffer selected by clicking its name in the
  // ladder table, falling back to the shallowest root row when nothing is
  // selected yet — so there's always somewhere to nest a new county/barony.
  const selectedRow =
    (selectedTitleId != null ? rows.find((row) => row.title_id === selectedTitleId) : undefined) ??
    tree[0]?.row ??
    null;
  // Plate I's tier span reads "Grand Principality · Piropa" — the realm's
  // own formal name plus whoever holds its crown, read off any row's own
  // " (crown)"-suffixed `sworn_to` (`almanach_reads`'s only place that
  // suffix appears) rather than a field the realm read doesn't carry.
  const crownHolder = rows
    .map((row) => row.sworn_to)
    .find((swornTo) => swornTo.endsWith(' (crown)'))
    ?.replace(/ \(crown\)$/, '');

  if (!payload) {
    return (
      <div className="almanach">
        <div className="wrap p-6 text-sm text-muted-foreground">Loading the ladder…</div>
      </div>
    );
  }

  return (
    <div className="almanach">
      <div className="bar">
        <span className="crumb">
          <span>Almanach de Catenys</span>
          <span>{realm?.name ?? `Realm ${realmId}`}</span>
        </span>
        <span className="right">
          <span className="mode">staff</span>
        </span>
      </div>
      <div className="almanac">
        <aside className="contents">
          <div className="mv">
            <span className="label">Realm</span>
            <ol>
              <li className="cur">The Ladder</li>
              <li className="ro">
                Charter
                <small>succession, particles, quiddities</small>
              </li>
            </ol>
          </div>
          <div className="mv">
            <span className="label">Houses</span>
            <ol>
              {houses.map((house) => (
                <li key={house.id} className={house.house_state === 'extinct' ? 'ro' : undefined}>
                  {house.house_state === 'extinct' ? (
                    <>
                      {house.name}
                      <small>extinct</small>
                    </>
                  ) : (
                    <Link to={`/staff/almanach/houses/${house.id}`}>{house.name}</Link>
                  )}
                </li>
              ))}
            </ol>
          </div>
        </aside>
        <main className="chapter">
          <h3>
            <RealmSwitcher realm={realm} realms={realms} realmId={realmId} />
            {(realm?.formal_name || crownHolder) && (
              <span className="tier">
                {[realm?.formal_name, crownHolder].filter(Boolean).join(' · ')}
              </span>
            )}
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
            selectedTitleId={selectedRow?.title_id ?? null}
            onSelectRow={(row) => setSelectedTitleId(row.title_id)}
          />
          <div className="savebar">
            <button
              type="button"
              className="btn quiet"
              disabled={!selectedRow}
              onClick={() => setPlantOpen(true)}
            >
              ⊕ plant a rung
            </button>
            <button
              type="button"
              className="btn ghost"
              disabled={!selectedRow}
              onClick={() => setBatchOpen(true)}
            >
              batch unclaimed…
            </button>
          </div>
        </main>
        <aside className="record">
          <h4>on record</h4>
          <dl>
            <dt>crown</dt>
            <dd>{crownHolder ?? <abbr title="none">—</abbr>}</dd>
            <dt>default tithe</dt>
            <dd>
              {realm?.default_tithe_pct != null ? (
                `${realm.default_tithe_pct}%`
              ) : (
                <abbr title="none">—</abbr>
              )}
            </dd>
          </dl>
        </aside>
      </div>
      {selectedRow && (
        <>
          <PlantRungDialog
            parent={{
              title_id: selectedRow.title_id,
              name: selectedRow.is_defined ? selectedRow.name : 'Undefined',
              tier: selectedRow.tier,
            }}
            open={plantOpen}
            onClose={() => setPlantOpen(false)}
            realmId={realmId}
            onConfirm={async (payload) => {
              const result = await plantMutation.mutateAsync({
                realm_id: realmId,
                parent_title_id: selectedRow.title_id,
                tier: payload.tier,
                name: payload.name,
                ...(payload.held_by_org_id != null
                  ? { held_by_org_id: payload.held_by_org_id }
                  : {}),
              });
              const newTitleId = result.data?.title_id;
              if (result.success !== false && typeof newTitleId === 'number') {
                setSelectedTitleId(newTitleId);
              }
            }}
          />
          <BatchUnclaimedDialog
            parent={{
              title_id: selectedRow.title_id,
              name: selectedRow.is_defined ? selectedRow.name : 'Undefined',
              tier: selectedRow.tier,
            }}
            open={batchOpen}
            onClose={() => setBatchOpen(false)}
            onConfirm={(payload) => {
              batchMutation.mutate({
                parent_title_id: selectedRow.title_id,
                tier: payload.tier,
                count: payload.count,
                ...(payload.baronies_per_county != null
                  ? { baronies_per_county: payload.baronies_per_county }
                  : {}),
              });
            }}
          />
        </>
      )}
    </div>
  );
}

export function AlmanachPage() {
  const { realmId: realmIdParam, houseId } = useParams<{ realmId?: string; houseId?: string }>();
  const { data: realmsPayload } = useRealms();

  if (houseId) {
    return <HouseDocument houseId={Number(houseId)} />;
  }

  if (!realmIdParam) {
    if (realmsPayload == null) {
      return <div className="almanach" />;
    }
    const realms = realmsPayload.results;
    if (realms.length > 0) {
      return <Navigate to={`/staff/almanach/realms/${realms[0].id}`} replace />;
    }
    return (
      <div className="almanach">
        <div className="wrap p-6 text-sm text-muted-foreground">No realms on record yet.</div>
      </div>
    );
  }

  return <RealmLadderPage realmId={Number(realmIdParam)} realms={realmsPayload?.results ?? []} />;
}

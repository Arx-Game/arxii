/**
 * AlmanachPage (#3983 Task 8) — the Almanach de Catenys staff house-builder's
 * route element for all three `/staff/almanach*` routes (`App.tsx`). With no
 * `:realmId`/`:houseId` it redirects to the first realm (or shows a bare
 * realm list when there are none yet, #3983 Task 8 decision 4); `:houseId`
 * is Task 9's house document (kept as a thin stub here so the route isn't
 * broken while that task is out); `:realmId` renders the realm ladder —
 * plates S-I/S-II's visual contract: the three-column `.almanac` grid
 * (contents rail | chapter | record rail), the realm name as a switcher
 * `<button>`, the `.lvl` level bar, the `.lad` disclosure table, and a save
 * bar dispatching `almanach_plant_rung`/`almanach_batch_unclaimed`.
 *
 * The record rail only shows fields this page's own reads actually carry
 * (`AlmanachRealm.default_tithe_pct`) — the plate's charter `<dl>` (crown,
 * succession law, particle, quiddities) needs realm/house data no Task 7 API
 * exposes yet, so it stays for a future Charter page rather than being
 * invented here.
 */
import { useEffect, useMemo, useState } from 'react';
import { Link, Navigate, useNavigate, useParams } from 'react-router-dom';

import { useAlmanachMutation, useHouses, useLadder, useRealms } from './queries';
import { buildLadderTree, defaultPressedTier } from './ladder/tree';
import { LevelBar } from './ladder/LevelBar';
import { LadderTable } from './ladder/LadderTable';
import { PlantRungDialog } from './ladder/PlantRungDialog';
import { BatchUnclaimedDialog } from './ladder/BatchUnclaimedDialog';
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
  // The general "plant/batch" savebar context — the shallowest rung on
  // record, so staff always have somewhere to nest a new county/barony
  // under. A row-specific plant/batch trigger is Task 9+ scope.
  const defaultParentRow = tree[0]?.row ?? null;

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
            {realm?.formal_name && <span className="tier">{realm.formal_name}</span>}
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
            selectedTitleId={selectedTitleId}
          />
          <div className="savebar">
            <button
              type="button"
              className="btn quiet"
              disabled={!defaultParentRow}
              onClick={() => setPlantOpen(true)}
            >
              ⊕ plant a rung
            </button>
            <button
              type="button"
              className="btn ghost"
              disabled={!defaultParentRow}
              onClick={() => setBatchOpen(true)}
            >
              batch unclaimed…
            </button>
          </div>
        </main>
        <aside className="record">
          <h4>on record</h4>
          <dl>
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
      {defaultParentRow && (
        <>
          <PlantRungDialog
            parent={{
              title_id: defaultParentRow.title_id,
              name: defaultParentRow.is_defined ? defaultParentRow.name : 'Undefined',
              tier: defaultParentRow.tier,
            }}
            open={plantOpen}
            onClose={() => setPlantOpen(false)}
            realmId={realmId}
            onConfirm={async (payload) => {
              const result = await plantMutation.mutateAsync({
                realm_id: realmId,
                parent_title_id: defaultParentRow.title_id,
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
              title_id: defaultParentRow.title_id,
              name: defaultParentRow.is_defined ? defaultParentRow.name : 'Undefined',
              tier: defaultParentRow.tier,
            }}
            open={batchOpen}
            onClose={() => setBatchOpen(false)}
            onConfirm={(payload) => {
              batchMutation.mutate({
                parent_title_id: defaultParentRow.title_id,
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

function HouseDocumentStub({ houseId }: { houseId: number }) {
  // Task 9 replaces this branch with the full house document (plates III-VIII).
  return (
    <div className="almanach">
      <div className="wrap p-6 text-sm text-muted-foreground">House {houseId}</div>
    </div>
  );
}

export function AlmanachPage() {
  const { realmId: realmIdParam, houseId } = useParams<{ realmId?: string; houseId?: string }>();
  const { data: realmsPayload } = useRealms();

  if (houseId) {
    return <HouseDocumentStub houseId={Number(houseId)} />;
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

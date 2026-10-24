/**
 * A domain's page (#4239): the title and who holds it, Location as realm,
 * tier and seat (the map is #4242), the demesne and its holdings, Books,
 * Forces, and the Vassals beneath with Create vassal domain and Add vacant
 * seats. A vacant title offers Create Family, which takes it.
 */
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

import { useAllHouses, useAlmanachMutation, useHoldingKinds, useTitleDocument } from '../queries';
import { RecordRail, type RecordRailDoor, type RecordRailRow } from '../document/RecordRail';
import { PlantRungDialog } from '../ladder/PlantRungDialog';
import { BatchUnclaimedDialog } from '../ladder/BatchUnclaimedDialog';
import { CreateFamilyForm } from '../front/CreateFamilyForm';
import { Picker } from '../shared/Picker';
import { Books, Forces } from '../shared/chapters';
import { houseUrl, orgUrl, personUrl, titleUrl } from '../shared/tier';
import '../almanach.css';

export function TitlePage({ titleId }: { titleId: number }) {
  const { data: doc } = useTitleDocument(titleId);
  const plant = useAlmanachMutation('almanach_plant_rung');
  const batch = useAlmanachMutation('almanach_batch_unclaimed');
  const setHolder = useAlmanachMutation('almanach_set_holder');
  const describe = useAlmanachMutation('almanach_describe_demesne');
  const nameRung = useAlmanachMutation('almanach_name_rung');
  const assignHolder = useAlmanachMutation('almanach_assign_holder');
  const vacateHolder = useAlmanachMutation('almanach_vacate_holder');
  const { data: housesPayload } = useAllHouses();
  const addHolding = useAlmanachMutation('almanach_add_holding');
  const { data: holdingKinds } = useHoldingKinds();
  const [rungName, setRungName] = useState('');
  const [seatHouseId, setSeatHouseId] = useState('');
  const [confirmVacate, setConfirmVacate] = useState(false);
  const [description, setDescription] = useState('');
  const [holdingKindId, setHoldingKindId] = useState<number | null>(null);
  const [holdingName, setHoldingName] = useState('');
  const [plantOpen, setPlantOpen] = useState(false);
  const [batchOpen, setBatchOpen] = useState(false);
  const [createFamily, setCreateFamily] = useState(false);

  useEffect(() => {
    setDescription(doc?.demesne?.description ?? '');
  }, [doc]);
  useEffect(() => {
    setRungName(doc?.title.name ?? '');
  }, [doc?.title.name]);
  useEffect(() => {
    const list = holdingKinds?.results ?? [];
    if (holdingKindId == null && list.length > 0) setHoldingKindId(list[0].id);
  }, [holdingKinds, holdingKindId]);

  if (!doc) {
    return (
      <div className="almanach">
        <div className="wrap p-6 text-sm text-muted-foreground">Loading the domain…</div>
      </div>
    );
  }
  const { title, demesne, holdings, books, forces, vassals } = doc;
  const parentRef = { title_id: title.title_id, name: title.name, tier: title.tier };

  const rows: RecordRailRow[] = [
    { label: 'tier', value: title.tier },
    { label: 'realm', value: title.realm },
    { label: 'held by', value: title.held_by || 'vacant' },
    { label: 'holder', value: title.holder || 'none' },
    { label: 'sworn to', value: title.sworn_to || 'none' },
    { label: 'seat', value: title.seat || 'none' },
    {
      label: 'holdings',
      value: `${holdings.length}, ${holdings.filter((h) => h.unsited).length} unsited`,
    },
    {
      label: 'vassals',
      value: `${vassals.length}, ${vassals.filter((v) => !v.held_by).length} vacant`,
    },
  ];
  const doors: RecordRailDoor[] = [];
  if (title.house_id != null) {
    doors.push({ label: title.held_by, to: houseUrl(title.house_id) });
    doors.push({ label: `${title.held_by} organization`, to: orgUrl(title.house_id) });
  }
  if (title.holder_id != null) doors.push({ label: title.holder, to: personUrl(title.holder_id) });
  doors.push({ label: `${title.realm} ladder`, to: `/staff/almanach/realms/${title.realm_id}` });

  return (
    <div className="almanach">
      <div className="bar">
        <span className="crumb">
          <span>
            <Link to="/staff/almanach">Almanach</Link>
          </span>
          <span>{title.realm}</span>
          <span>{title.name || 'unnamed'}</span>
        </span>
        <span className="right">
          <span className="status">{title.house_id != null ? 'held' : 'vacant'}</span>
          <span className="mode">staff</span>
        </span>
      </div>
      <div className="almanac">
        <aside className="contents">
          {title.sworn_to && (
            <div className="mv">
              <span className="label">Above</span>
              <ol>
                <li>{title.sworn_to}</li>
              </ol>
            </div>
          )}
          <div className="mv">
            <span className="label">This rung</span>
            <ol>
              <li className="cur">
                {title.name || 'unnamed'}
                <small>{title.held_by || 'vacant'}</small>
              </li>
            </ol>
          </div>
          <div className="mv">
            <span className="label">Vassals</span>
            <ol>
              {vassals.map((v) => (
                <li key={v.title_id}>
                  <Link to={titleUrl(v.title_id)}>{v.name || 'unnamed'}</Link>
                  <small>{v.held_by || 'vacant'}</small>
                </li>
              ))}
            </ol>
          </div>
        </aside>
        <main className="chapter">
          <h3>
            {title.name || 'unnamed'}{' '}
            <span className="tier">
              {title.tier} · {title.realm}
            </span>
          </h3>
          <div className="field">
            <label htmlFor="r-name">name</label>
            <input
              id="r-name"
              type="text"
              value={rungName}
              onChange={(e) => setRungName(e.target.value)}
            />{' '}
            <button
              type="button"
              className="btn sm quiet"
              disabled={rungName.trim() === '' || rungName.trim() === title.name}
              onClick={() => nameRung.mutate({ title_id: titleId, name: rungName.trim() })}
            >
              {title.name ? 'Rename' : 'Name'}
            </button>
          </div>
          <div className="row3">
            <div className="field">
              <span className="label">held by</span>
              <div className="pick">
                {title.house_id != null ? (
                  <>
                    <Link to={houseUrl(title.house_id)}>{title.held_by}</Link>
                    {title.holder_id != null && (
                      <span className="meta">
                        <Link to={personUrl(title.holder_id)}>{title.holder}</Link>
                      </span>
                    )}
                    <Picker
                      kind="person"
                      placeholder="holder"
                      ariaLabel="holder"
                      onPick={(hit) => setHolder.mutate({ title_id: titleId, node_id: hit.id })}
                    />
                  </>
                ) : (
                  <button type="button" className="new" onClick={() => setCreateFamily(true)}>
                    Create Family
                  </button>
                )}
              </div>
            </div>
            <div className="field">
              <span className="label">sworn to</span>
              <div className="val">{title.sworn_to || <span className="meta">none</span>}</div>
            </div>
            <div className="field">
              <span className="label">succession</span>
              <div className="val">{title.succession || <span className="meta">none</span>}</div>
            </div>
          </div>
          {title.chain_top_id === title.title_id && (
            <div className="field">
              <label htmlFor="r-house">house</label>
              <select
                id="r-house"
                value={seatHouseId}
                onChange={(e) => setSeatHouseId(e.target.value)}
              >
                <option value="">pick a house</option>
                {(housesPayload?.results ?? [])
                  .filter((house) => house.id !== title.house_id)
                  .map((house) => (
                    <option key={house.id} value={house.id}>
                      {house.name}
                    </option>
                  ))}
              </select>{' '}
              <button
                type="button"
                className="btn sm quiet"
                disabled={seatHouseId === ''}
                onClick={() => {
                  assignHolder.mutate({ title_id: titleId, org_id: Number(seatHouseId) });
                  setSeatHouseId('');
                }}
              >
                Seat
              </button>
            </div>
          )}
          {title.chain_top_id === title.title_id && title.house_id != null && (
            <div className="field">
              {confirmVacate ? (
                <>
                  <button
                    type="button"
                    className="btn sm quiet"
                    onClick={() => {
                      vacateHolder.mutate({ title_id: titleId });
                      setConfirmVacate(false);
                    }}
                  >
                    Confirm vacate {title.held_by}
                  </button>{' '}
                  <button
                    type="button"
                    className="btn sm ghost"
                    onClick={() => setConfirmVacate(false)}
                  >
                    Cancel
                  </button>
                </>
              ) : (
                <button
                  type="button"
                  className="btn sm quiet"
                  onClick={() => setConfirmVacate(true)}
                >
                  Vacate
                </button>
              )}
            </div>
          )}
          {createFamily && (
            <CreateFamilyForm
              vacantTitle={{ title_id: title.title_id, name: title.name, realm_id: title.realm_id }}
              onCancel={() => setCreateFamily(false)}
              onCreated={() => setCreateFamily(false)}
            />
          )}

          <h4 className="sec">Location</h4>
          <div className="row3">
            <div className="field">
              <span className="label">realm</span>
              <div className="val">{title.realm}</div>
            </div>
            <div className="field">
              <span className="label">tier</span>
              <div className="val">{title.tier}</div>
            </div>
            <div className="field">
              <span className="label">seat</span>
              <div className="val">{title.seat || <span className="meta">none</span>}</div>
            </div>
          </div>
          {demesne && (
            <>
              <div className="field">
                <label htmlFor="d-desc">demesne</label>
                <textarea
                  id="d-desc"
                  className="prose"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                />
              </div>
              <div className="row3">
                <div className="field">
                  <span className="label">hall</span>
                  <div className="val">{demesne.hall || <span className="meta">none</span>}</div>
                </div>
                <div className="field">
                  <span className="label">population</span>
                  <div className="val">{demesne.population}</div>
                </div>
                <div className="field">
                  <span className="label">prosperity</span>
                  <div className="val">{demesne.prosperity}</div>
                </div>
              </div>
            </>
          )}

          <h4 className="sec">Holdings</h4>
          <div className="scroll">
            <table className="lad">
              <thead>
                <tr>
                  <th scope="col">holding</th>
                  <th scope="col">type</th>
                  <th scope="col">site</th>
                  <th scope="col">state</th>
                </tr>
              </thead>
              <tbody>
                {holdings.map((h) => (
                  <tr key={h.holding_id}>
                    <td>{h.name || h.kind}</td>
                    <td>{h.kind}</td>
                    <td>{h.site || <span className="meta">none</span>}</td>
                    <td>{h.unsited ? <span className="chip undef">unsited</span> : 'working'}</td>
                  </tr>
                ))}
                {holdings.length === 0 && (
                  <tr>
                    <td colSpan={4} className="meta">
                      none
                    </td>
                  </tr>
                )}
                {demesne && (
                  <tr>
                    <td colSpan={4}>
                      <div className="row3">
                        <div className="field">
                          <label htmlFor="h-kind">Add holding</label>
                          <select
                            id="h-kind"
                            value={holdingKindId ?? ''}
                            onChange={(e) =>
                              setHoldingKindId(
                                e.target.value === '' ? null : Number(e.target.value)
                              )
                            }
                          >
                            {(holdingKinds?.results ?? []).map((k) => (
                              <option key={k.id} value={k.id}>
                                {k.name}
                              </option>
                            ))}
                          </select>
                        </div>
                        <div className="field">
                          <label htmlFor="h-name">name</label>
                          <input
                            id="h-name"
                            type="text"
                            value={holdingName}
                            onChange={(e) => setHoldingName(e.target.value)}
                          />
                        </div>
                        <div className="field">
                          <span className="label">&nbsp;</span>
                          <button
                            type="button"
                            className="btn sm quiet"
                            disabled={holdingKindId == null}
                            onClick={() => {
                              addHolding.mutate({
                                domain_id: demesne.domain_id,
                                holding_kind_id: holdingKindId,
                                name: holdingName.trim(),
                                unsited: true,
                              });
                              setHoldingName('');
                            }}
                          >
                            Add holding
                          </button>
                        </div>
                      </div>
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          <Books books={books} />
          <Forces forces={forces} />

          <h4 className="sec">Vassals</h4>
          <div className="scroll">
            <table className="lad">
              <thead>
                <tr>
                  <th scope="col">title</th>
                  <th scope="col">held by</th>
                  <th scope="col" className="n">
                    demesne
                  </th>
                  <th scope="col" className="n">
                    vassals
                  </th>
                </tr>
              </thead>
              <tbody>
                {vassals.map((v) => (
                  <tr key={v.title_id}>
                    <td>
                      <Link to={titleUrl(v.title_id)}>{v.name || 'unnamed'}</Link>
                    </td>
                    <td>{v.held_by || <span className="chip open">vacant</span>}</td>
                    <td className="n">{v.demesne}</td>
                    <td className="n">{v.vassals}</td>
                  </tr>
                ))}
                <tr>
                  <td colSpan={4}>
                    <button type="button" className="add" onClick={() => setPlantOpen(true)}>
                      Create vassal domain
                    </button>{' '}
                    <span className="meta">·</span>{' '}
                    <button type="button" className="add" onClick={() => setBatchOpen(true)}>
                      Add vacant seats
                    </button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          {demesne && (
            <div className="savebar">
              <button
                type="button"
                className="btn"
                onClick={() => describe.mutate({ domain_id: demesne.domain_id, description })}
              >
                Save
              </button>
            </div>
          )}
        </main>
        <RecordRail rows={rows} doors={doors} />
      </div>
      <PlantRungDialog
        parent={parentRef}
        open={plantOpen}
        realmId={title.realm_id}
        onClose={() => setPlantOpen(false)}
        onConfirm={(payload) => {
          setPlantOpen(false);
          plant.mutate({
            realm_id: title.realm_id,
            tier: payload.tier,
            name: payload.name,
            parent_title_id: title.title_id,
            ...(payload.held_by_org_id != null ? { held_by_org_id: payload.held_by_org_id } : {}),
          });
        }}
      />
      <BatchUnclaimedDialog
        parent={parentRef}
        open={batchOpen}
        onClose={() => setBatchOpen(false)}
        onConfirm={(payload) => {
          setBatchOpen(false);
          batch.mutate({
            parent_title_id: title.title_id,
            tier: payload.tier,
            count: payload.count,
            ...(payload.baronies_per_county != null
              ? { baronies_per_county: payload.baronies_per_county }
              : {}),
          });
        }}
      />
    </div>
  );
}

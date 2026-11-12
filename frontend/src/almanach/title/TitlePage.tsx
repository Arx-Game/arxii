/**
 * A domain's page (#4239): the title, who holds it and its ruler (#5017), Location as realm,
 * tier and seat (the map is #4242), the demesne and its holdings, Books,
 * Forces, and the Vassals beneath with Create vassal domain and Add vacant
 * seats. A vacant title offers Create Family, which takes it.
 */
import { Globe } from 'lucide-react';
import { Fragment, useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import {
  useAllHouses,
  useAlmanachMutation,
  useHoldingKinds,
  useRealmTitles,
  useRegionalEventKinds,
  useTitleDocument,
} from '../queries';
import { RecordRail, type RecordRailDoor, type RecordRailRow } from '../document/RecordRail';
import type { AlmanachRealmRowSummary } from '../types';
import { HoldingRow } from './HoldingRow';
import { RulerSlot } from './RulerSlot';
import { PlantRungDialog } from '../ladder/PlantRungDialog';
import { BatchUnclaimedDialog } from '../ladder/BatchUnclaimedDialog';
import { CreateFamilyForm } from '../front/CreateFamilyForm';
import { Books, Forces } from '../shared/chapters';
import { houseUrl, orgUrl, personUrl, titleUrl } from '../shared/tier';
import { SECTIONS, STATES } from '../copy';
import { useRegionMapsQuery } from '@/world-builder/queries';
import { useAccount } from '@/store/hooks';
import { rememberMapFocus } from '@/world-builder/atlas/mapFocus';
import { Crumbs } from '../shared/Crumbs';
import '../almanach.css';

export function TitlePage({ titleId }: { titleId: number }) {
  const { data: doc, error, refetch } = useTitleDocument(titleId);
  const plant = useAlmanachMutation('almanach_plant_rung');
  const batch = useAlmanachMutation('almanach_batch_unclaimed');
  const describe = useAlmanachMutation('almanach_describe_demesne');
  const nameRung = useAlmanachMutation('almanach_name_rung');
  const deleteRung = useAlmanachMutation('almanach_delete_rung');
  const moveRung = useAlmanachMutation('almanach_move_rung');
  const navigate = useNavigate();
  const { data: realmTitles } = useRealmTitles(doc?.title.realm_id);
  const assignHolder = useAlmanachMutation('almanach_assign_holder');
  const vacateHolder = useAlmanachMutation('almanach_vacate_holder');
  const { data: housesPayload } = useAllHouses();
  const addHolding = useAlmanachMutation('almanach_add_holding');
  const setCapacity = useAlmanachMutation('almanach_set_capacity');
  const [capacityText, setCapacityText] = useState('');
  // #5080: a blight, a war, a famine over this land
  const openEvent = useAlmanachMutation('almanach_open_regional_event');
  const closeEvent = useAlmanachMutation('almanach_close_regional_event');
  const [eventKindId, setEventKindId] = useState('');
  const [severityText, setSeverityText] = useState('100');
  const { data: eventKinds } = useRegionalEventKinds();
  const { data: holdingKinds } = useHoldingKinds();
  const { data: regionMaps } = useRegionMapsQuery();
  const account = useAccount();
  const [rungName, setRungName] = useState('');
  // The name the field last sent (#5017): Enter and then a blur, or a blur and then
  // Enter, save once; the document's refetch clears it.
  const [sentName, setSentName] = useState<string | null>(null);
  const [moveTo, setMoveTo] = useState('');
  const [confirmDelete, setConfirmDelete] = useState(false);
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
    setSentName(null);
  }, [doc?.title.name]);
  useEffect(() => {
    const list = holdingKinds?.results ?? [];
    if (holdingKindId == null && list.length > 0) setHoldingKindId(list[0].id);
  }, [holdingKinds, holdingKindId]);

  if (!doc) {
    // A failed request says so instead of reading "Loading" forever (#5011).
    return (
      <div className="almanach">
        <div className="wrap p-6 text-sm text-muted-foreground">
          {error ? (
            <>
              <p role="alert">{error.message}</p>
              <button type="button" className="btn sm quiet" onClick={() => void refetch()}>
                Try again
              </button>
            </>
          ) : (
            'Loading the domain…'
          )}
        </div>
      </div>
    );
  }
  const { title, demesne, holdings, books, forces, vassals, events } = doc;
  const { chartered_fiefs: charteredFiefs, chartered_by: charteredBy, claims, chain } = doc;
  // Land is a county or a barony (#5069): only land has a demesne, developments and
  // forces; a duchy and above are organization, their holdings the rungs beneath.
  const isBarony = title.tier === 'barony';
  const isCounty = title.tier === 'county' || title.tier === 'march';
  const heldHere = (v: AlmanachRealmRowSummary) => v.held_by !== '' && v.held_by === title.held_by;
  const heldRows = vassals.filter(heldHere);
  const vassalRows = vassals.filter((v) => !heldHere(v));
  const people = (n: number) => n.toLocaleString('en-US');
  const terrainWords = (demesne?.terrain ?? []).map((t) => t.label.toLowerCase()).join(', ');
  const sendCapacity = (capacity: number | null) => {
    if (demesne == null) return;
    setCapacity.mutate({ domain_id: demesne.domain_id, capacity });
    setCapacityText('');
  };
  const parentRef = { title_id: title.title_id, name: title.name, tier: title.tier };
  const stationWords = { titular: STATES.titular, potential: STATES.potential } as const;
  const stationWord =
    title.station === 'titular' || title.station === 'potential'
      ? stationWords[title.station]
      : null;
  const firstRegionMap = regionMaps?.[0] ?? null;
  const saveName = () => {
    const next = rungName.trim();
    if (next === '' || next === title.name || next === sentName) return;
    setSentName(next);
    nameRung.mutate({ title_id: titleId, name: next });
  };

  const rows: RecordRailRow[] = [
    { label: 'tier', value: title.tier },
    { label: 'realm', value: title.realm },
    { label: 'held by', value: title.held_by || 'vacant' },
    { label: 'ruler', value: title.holder || 'undefined' },
    { label: 'sworn to', value: title.sworn_to || 'none' },
    { label: 'seat', value: title.seat || 'none' },
    ...(demesne
      ? [
          { label: 'people', value: people(demesne.population) },
          {
            label: 'developments',
            value: `${holdings.length}, ${holdings.filter((h) => h.unsited).length} unsited`,
          },
        ]
      : []),
    { label: 'held', value: `${heldRows.length}` },
    {
      label: 'vassals',
      value: `${vassalRows.length}, ${vassalRows.filter((v) => !v.held_by).length} vacant`,
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
        <Crumbs
          trail={[
            { label: 'Almanach', to: '/staff/almanach' },
            ...chain.map((link) => ({
              label: link.name || `unnamed ${link.tier}`,
              to:
                link.title_id == null
                  ? `/staff/almanach/realms/${title.realm_id}`
                  : titleUrl(link.title_id),
            })),
            { label: title.name || 'unnamed' },
          ]}
        />
        <span className="right">
          <span className="status">
            {stationWord ?? (title.house_id != null ? 'held' : 'vacant')}
          </span>
          <span className="mode">staff</span>
        </span>
      </div>
      <div className="almanac">
        <aside className="contents">
          {chain.length > 0 && (
            <div className="mv" data-testid="title-chain">
              <span className="label">Above</span>
              <ol>
                {chain.map((link) => (
                  <li key={`${link.tier}-${link.title_id ?? 'realm'}`}>
                    <Link
                      to={
                        link.title_id == null
                          ? `/staff/almanach/realms/${title.realm_id}`
                          : titleUrl(link.title_id)
                      }
                    >
                      {link.name || `unnamed ${link.tier}`}
                    </Link>
                    <small>{link.tier}</small>
                  </li>
                ))}
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
            <span className="label">{SECTIONS.holdings}</span>
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
            </span>{' '}
            {firstRegionMap && (
              <Link
                className="btn sm quiet icon"
                to="/staff/world-builder"
                aria-label="View on the map"
                title="View on the map"
                onClick={() =>
                  rememberMapFocus(account?.id ?? 'anon', firstRegionMap.id, title.title_id)
                }
              >
                <Globe className="h-4 w-4" aria-hidden="true" />
              </Link>
            )}
          </h3>
          <div className="field">
            <input
              id="r-name"
              type="text"
              aria-label="Name"
              placeholder="Name"
              value={rungName}
              onChange={(e) => setRungName(e.target.value)}
              onBlur={saveName}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault();
                  saveName();
                }
              }}
            />
          </div>
          <div className="row3">
            <div className="field">
              <span className="label">held by</span>
              <div className="pick">
                {title.house_id != null ? (
                  <>
                    <Link to={houseUrl(title.house_id)}>{title.held_by}</Link>
                    <span className="meta">
                      <RulerSlot
                        titleId={titleId}
                        houseId={title.house_id}
                        holderId={title.holder_id}
                        holderName={title.holder}
                      />
                    </span>
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
              <div className="val">
                {title.sworn_to || <span className="meta">none</span>}
                {title.pledged_liege && (
                  <span className="meta">{`pledged to ${title.pledged_liege.name}`}</span>
                )}
              </div>
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
          {title.chain_top_id === title.title_id && (
            <div className="field">
              <label htmlFor="r-move">move under</label>
              <select id="r-move" value={moveTo} onChange={(e) => setMoveTo(e.target.value)}>
                <option value="">pick a rung</option>
                {(realmTitles?.results ?? [])
                  .filter((t) => t.id !== title.title_id)
                  .map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.name || 'unnamed'} ({t.tier})
                    </option>
                  ))}
              </select>{' '}
              <button
                type="button"
                className="btn sm quiet"
                disabled={moveTo === ''}
                onClick={() => {
                  moveRung.mutate({ title_id: titleId, parent_title_id: Number(moveTo) });
                  setMoveTo('');
                }}
              >
                Move
              </button>
              {title.house_id == null &&
                (confirmDelete ? (
                  <>
                    {' '}
                    <button
                      type="button"
                      className="btn sm quiet"
                      onClick={() => {
                        deleteRung.mutate(
                          { title_id: titleId },
                          {
                            onSuccess: (result) => {
                              if (result.success !== false) {
                                navigate(`/staff/almanach/realms/${title.realm_id}`);
                              }
                            },
                          }
                        );
                        setConfirmDelete(false);
                      }}
                    >
                      Confirm delete {title.name || 'rung'}
                    </button>{' '}
                    <button
                      type="button"
                      className="btn sm ghost"
                      onClick={() => setConfirmDelete(false)}
                    >
                      Cancel
                    </button>
                  </>
                ) : (
                  <>
                    {' '}
                    <button
                      type="button"
                      className="btn sm quiet"
                      onClick={() => setConfirmDelete(true)}
                    >
                      Delete rung
                    </button>
                  </>
                ))}
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
              {isCounty && <h4 className="sec">{SECTIONS.hinterland}</h4>}
              <div className="land">
                <div className="row3">
                  <div className="field">
                    <span className="label">population</span>
                    <div className="val">{people(demesne.population)}</div>
                  </div>
                  <div className="field">
                    <span className="label">capacity</span>
                    <div className="val">
                      {people(demesne.population_capacity)}
                      {demesne.capacity_override != null && (
                        <span className="meta"> set by hand</span>
                      )}
                    </div>
                  </div>
                  <div className="field">
                    <span className="label">prosperity</span>
                    <div className="val">{demesne.prosperity}</div>
                  </div>
                </div>
                <div className="row3">
                  <div className="field">
                    <span className="label">terrain</span>
                    <div className="val">{terrainWords || <span className="meta">none</span>}</div>
                  </div>
                  <div className="field">
                    <span className="label">unrest</span>
                    <div className="val">{demesne.unrest}</div>
                  </div>
                  <div className="field">
                    <span className="label">hall</span>
                    <div className="val">{demesne.hall || <span className="meta">none</span>}</div>
                  </div>
                </div>
                {isBarony && (
                  <div className="field">
                    <div className="row3">
                      <div className="field">
                        <input
                          id="d-capacity"
                          type="number"
                          min={0}
                          aria-label="capacity"
                          placeholder="capacity"
                          value={capacityText}
                          onChange={(e) => setCapacityText(e.target.value)}
                        />
                      </div>
                      <div className="field">
                        <button
                          type="button"
                          className="btn sm quiet"
                          disabled={capacityText.trim() === ''}
                          onClick={() => sendCapacity(Number(capacityText))}
                        >
                          Set
                        </button>{' '}
                        <button
                          type="button"
                          className="btn sm ghost"
                          disabled={demesne.capacity_override == null}
                          onClick={() => sendCapacity(null)}
                        >
                          Terrain
                        </button>
                      </div>
                    </div>
                  </div>
                )}
                <div className="field">
                  <label htmlFor="d-desc">description</label>
                  <textarea
                    id="d-desc"
                    className="prose"
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                  />
                </div>
              </div>

              <h4 className="sec">{SECTIONS.developments}</h4>
            </>
          )}
          {demesne && (
            <div className="scroll">
              <table className="lad">
                <thead>
                  <tr>
                    <th scope="col">holding</th>
                    <th scope="col">type</th>
                    <th scope="col">site</th>
                    <th scope="col">state</th>
                    <th scope="col">
                      <span className="sr-only">actions</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {holdings.map((h) => (
                    <HoldingRow
                      key={h.holding_id}
                      holding={h}
                      kind={(holdingKinds?.results ?? []).find((k) => k.name === h.kind)}
                    />
                  ))}
                  {holdings.length === 0 && (
                    <tr>
                      <td colSpan={5} className="meta">
                        none
                      </td>
                    </tr>
                  )}
                  {demesne && (
                    <tr>
                      <td colSpan={5}>
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
          )}

          <Books books={books} />
          {demesne && <Forces forces={forces} />}

          <h4 className="sec">{SECTIONS.events}</h4>
          <div className="events">
            {events.length === 0 && <p className="meta">none</p>}
            {events.map((event) => (
              <div key={event.event_id} className="row2 ev">
                <div className="field">
                  <div className="val">
                    <strong>{event.kind}</strong> over {event.area}{' '}
                    <span className="meta">{event.severity_pct}%</span>
                  </div>
                </div>
                <div className="field">
                  <button
                    type="button"
                    className="btn sm ghost"
                    onClick={() => closeEvent.mutate({ event_id: event.event_id })}
                  >
                    Close
                  </button>
                </div>
              </div>
            ))}
            <div className="row3">
              <div className="field">
                <select
                  id="d-event-kind"
                  aria-label="event"
                  value={eventKindId}
                  onChange={(e) => setEventKindId(e.target.value)}
                >
                  <option value="">Event</option>
                  {(eventKinds?.results ?? []).map((kind) => (
                    <option key={kind.id} value={kind.id}>
                      {kind.name}
                    </option>
                  ))}
                </select>
              </div>
              <div className="field">
                <input
                  id="d-event-severity"
                  type="number"
                  min={1}
                  max={100}
                  aria-label="severity"
                  value={severityText}
                  onChange={(e) => setSeverityText(e.target.value)}
                />
              </div>
              <div className="field">
                <button
                  type="button"
                  className="btn sm quiet"
                  disabled={eventKindId === '' || severityText.trim() === ''}
                  onClick={() => {
                    openEvent.mutate({
                      kind_id: Number(eventKindId),
                      area_id: title.area_id,
                      severity_pct: Number(severityText),
                    });
                    setEventKindId('');
                    setSeverityText('100');
                  }}
                >
                  Open
                </button>
              </div>
            </div>
          </div>

          <h4 className="sec">{SECTIONS.holdings}</h4>
          <div className="scroll">
            <table className="lad">
              <thead>
                <tr>
                  <th scope="col">title</th>
                  <th scope="col">held by</th>
                  <th scope="col" className="n">
                    population
                  </th>
                  <th scope="col" className="n">
                    vassals
                  </th>
                </tr>
              </thead>
              <tbody>
                {vassals.length > 0 &&
                  (
                    [
                      [SECTIONS.held, heldRows],
                      [SECTIONS.vassals, vassalRows],
                    ] as const
                  ).map(([word, group]) => (
                    <Fragment key={word}>
                      <tr className="grp">
                        <th scope="rowgroup" colSpan={4}>
                          {word}
                        </th>
                      </tr>
                      {group.map((v) => (
                        <tr key={v.title_id}>
                          <td>
                            <Link to={titleUrl(v.title_id)}>{v.name || 'unnamed'}</Link>
                          </td>
                          <td>{v.held_by || <span className="chip open">vacant</span>}</td>
                          <td className="n">{people(v.population)}</td>
                          <td className="n">{v.vassals}</td>
                        </tr>
                      ))}
                      {group.length === 0 && (
                        <tr>
                          <td colSpan={4}>
                            <span className="meta">none</span>
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  ))}
                {vassals.length === 0 && (
                  <tr>
                    <td colSpan={4}>
                      <span className="meta">nothing</span>
                    </td>
                  </tr>
                )}
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
          <h4 className="sec">{SECTIONS.historical_charter}</h4>
          <div className="scroll">
            <table className="lad">
              <thead>
                <tr>
                  <th scope="col">title</th>
                  <th scope="col">tier</th>
                  <th scope="col">basis</th>
                </tr>
              </thead>
              <tbody>
                {charteredFiefs.map((fief) => (
                  <tr key={fief.title_id}>
                    <td>
                      <Link to={titleUrl(fief.title_id)}>{fief.name || 'unnamed'}</Link>
                    </td>
                    <td>{fief.tier}</td>
                    <td>{fief.basis || <abbr title="none">—</abbr>}</td>
                  </tr>
                ))}
                {charteredFiefs.length === 0 && (
                  <tr>
                    <td colSpan={3}>
                      <span className="meta">nothing chartered</span>
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
            {charteredBy.length > 0 && (
              <p className="meta">
                in the charter of{' '}
                {charteredBy.map((row, index) => (
                  <span key={row.title_id}>
                    {index > 0 ? ', ' : ''}
                    <Link to={titleUrl(row.title_id)}>{row.name || `unnamed ${row.tier}`}</Link>
                  </span>
                ))}
              </p>
            )}
            <ul className="claims">
              {claims.map((claim) => (
                <li key={claim.claim_id}>
                  <span>{`claimed by ${claim.claimant}`}</span>{' '}
                  {claim.basis && <small>{claim.basis}</small>}
                </li>
              ))}
            </ul>
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

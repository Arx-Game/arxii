/**
 * The crime family's chapters (#4239, #4081 folded in): its wards, the gangs
 * beneath with their neighborhoods, the crews on rooms. The same ladder table
 * as the nobles' with the columns renamed. Areas and rooms are picked by id
 * until the Atlas link (#4242) gives them a map.
 */
import { useState } from 'react';
import { Link } from 'react-router-dom';

import { useAlmanachMutation } from '../queries';
import type { AlmanachTurf } from '../types';
import { orgUrl } from '../shared/tier';

export function TurfChapter({
  houseId,
  houseName,
  turf,
}: {
  houseId: number;
  houseName: string;
  turf: AlmanachTurf | null;
}) {
  const claimWard = useAlmanachMutation('almanach_claim_ward');
  const addGang = useAlmanachMutation('almanach_add_gang');
  const openSlot = useAlmanachMutation('almanach_open_crew_slot');
  const [wardArea, setWardArea] = useState('');
  const [gangName, setGangName] = useState('');
  const [gangArea, setGangArea] = useState('');
  const [slotGang, setSlotGang] = useState<number | null>(turf?.gangs[0]?.org_id ?? null);
  const [slotName, setSlotName] = useState('');
  const [slotRooms, setSlotRooms] = useState('');

  return (
    <main className="chapter">
      <h3>
        Turf <span className="tier">{houseName}</span>
      </h3>
      <div className="row3">
        <div className="field">
          <span className="label">tier</span>
          <div className="val">{turf?.tier || <span className="meta">none</span>}</div>
        </div>
        <div className="field">
          <span className="label">wards</span>
          <div className="val">
            {turf && turf.wards.length > 0 ? (
              turf.wards
                .map(
                  (w) =>
                    `${w.name} · grip ${w.grip}${w.base_value ? ` · ${w.base_value.toLocaleString()} c / week` : ''}`
                )
                .join(', ')
            ) : (
              <span className="meta">none</span>
            )}
          </div>
        </div>
        <div className="field">
          <label htmlFor="turf-ward">Claim ward</label>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <input
              id="turf-ward"
              type="number"
              placeholder="area id"
              value={wardArea}
              onChange={(e) => setWardArea(e.target.value)}
            />
            <button
              type="button"
              className="btn sm quiet"
              disabled={wardArea.trim() === ''}
              onClick={() => {
                claimWard.mutate({ organization_id: houseId, area_id: Number(wardArea) });
                setWardArea('');
              }}
            >
              Claim ward
            </button>
          </div>
        </div>
      </div>

      <h4 className="sec">Gangs</h4>
      <div className="scroll">
        <table className="lad">
          <thead>
            <tr>
              <th scope="col">gang</th>
              <th scope="col">boss</th>
              <th scope="col">neighborhood</th>
              <th scope="col" className="n">
                crews
              </th>
            </tr>
          </thead>
          <tbody>
            {(turf?.gangs ?? []).map((g) => (
              <>
                <tr key={g.org_id}>
                  <td>
                    <Link to={orgUrl(g.org_id)}>{g.name}</Link>
                  </td>
                  <td>{g.boss || <span className="chip open">boss seat open</span>}</td>
                  <td>{g.neighborhood}</td>
                  <td className="n">{g.crews.length}</td>
                </tr>
                {g.crews.map((c) => (
                  <tr key={`crew-${c.crew_slot_id}`} className="d1">
                    <td>
                      {c.is_open && <span className="chip open">open</span>} {c.name}
                    </td>
                    <td>{c.claimed_by || <span className="chip open">vacant</span>}</td>
                    <td>
                      {c.rooms} {c.rooms === 1 ? 'room' : 'rooms'}
                    </td>
                    <td className="n" />
                  </tr>
                ))}
              </>
            ))}
            <tr>
              <td colSpan={4}>
                <div className="row3">
                  <div className="field">
                    <label htmlFor="gang-name">Add gang</label>
                    <input
                      id="gang-name"
                      type="text"
                      placeholder="name"
                      value={gangName}
                      onChange={(e) => setGangName(e.target.value)}
                    />
                  </div>
                  <div className="field">
                    <label htmlFor="gang-area">neighborhood</label>
                    <input
                      id="gang-area"
                      type="number"
                      placeholder="area id"
                      value={gangArea}
                      onChange={(e) => setGangArea(e.target.value)}
                    />
                  </div>
                  <div className="field">
                    <span className="label">&nbsp;</span>
                    <button
                      type="button"
                      className="btn sm quiet"
                      disabled={gangName.trim() === '' || gangArea.trim() === ''}
                      onClick={() => {
                        addGang.mutate({
                          family_org_id: houseId,
                          name: gangName.trim(),
                          neighborhood_area_id: Number(gangArea),
                        });
                        setGangName('');
                        setGangArea('');
                      }}
                    >
                      Add gang
                    </button>
                  </div>
                </div>
                {(turf?.gangs ?? []).length > 0 && (
                  <div className="row3">
                    <div className="field">
                      <label htmlFor="slot-gang">Open crew slot</label>
                      <select
                        id="slot-gang"
                        value={slotGang ?? ''}
                        onChange={(e) =>
                          setSlotGang(e.target.value === '' ? null : Number(e.target.value))
                        }
                      >
                        {(turf?.gangs ?? []).map((g) => (
                          <option key={g.org_id} value={g.org_id}>
                            {g.name}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div className="field">
                      <label htmlFor="slot-name">name</label>
                      <input
                        id="slot-name"
                        type="text"
                        value={slotName}
                        onChange={(e) => setSlotName(e.target.value)}
                      />
                    </div>
                    <div className="field">
                      <label htmlFor="slot-rooms">room ids</label>
                      <div style={{ display: 'flex', gap: '0.5rem' }}>
                        <input
                          id="slot-rooms"
                          type="text"
                          placeholder="12, 13"
                          value={slotRooms}
                          onChange={(e) => setSlotRooms(e.target.value)}
                        />
                        <button
                          type="button"
                          className="btn sm quiet"
                          disabled={
                            slotGang == null || slotName.trim() === '' || slotRooms.trim() === ''
                          }
                          onClick={() => {
                            openSlot.mutate({
                              gang_id: slotGang,
                              name: slotName.trim(),
                              room_ids: slotRooms
                                .split(',')
                                .map((v) => Number(v.trim()))
                                .filter((v) => v > 0),
                            });
                            setSlotName('');
                            setSlotRooms('');
                          }}
                        >
                          Open crew slot
                        </button>
                      </div>
                    </div>
                  </div>
                )}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </main>
  );
}

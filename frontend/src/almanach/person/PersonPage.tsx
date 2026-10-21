/**
 * A person's page (#4239). Every link is a slot: family, kin, house, titles,
 * sheet. Kin names are links so staff move person to person. NPC tier is a
 * 0/1/2/3 seg that only rises and reads long after the name; Status is Alive
 * / RIP / Missing with the record's accuracy and its obituary. A player
 * character's name and tier are never edited here.
 */
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

import { useAlmanachMutation, useGenders, usePersonDocument, useUnionKinds } from '../queries';
import type { PersonDocument, SearchHit } from '../types';
import { RecordRail, type RecordRailDoor, type RecordRailRow } from '../document/RecordRail';
import { CreateFamilyForm } from '../front/CreateFamilyForm';
import { Picker } from '../shared/Picker';
import {
  familyUrl,
  houseUrl,
  NPC_TIERS,
  orgUrl,
  personUrl,
  statusMark,
  tierMark,
  titleUrl,
} from '../shared/tier';
import '../almanach.css';

type Status = PersonDocument['person']['status'];
type Link_ = 'parent' | 'child' | 'spouse';

const STATUS_LABELS: Record<Status, string> = { alive: 'Alive', rip: 'RIP', missing: 'Missing' };

export function PersonPage({ personId }: { personId: number }) {
  const { data: doc } = usePersonDocument(personId);
  const { data: genders } = useGenders();
  const { data: unionKinds } = useUnionKinds(null);
  const editPerson = useAlmanachMutation('almanach_edit_person');
  const setStatus = useAlmanachMutation('almanach_set_status');
  const promote = useAlmanachMutation('almanach_promote_kin');
  const setAppable = useAlmanachMutation('almanach_set_appable');
  const attachSheet = useAlmanachMutation('almanach_attach_sheet');
  const createKin = useAlmanachMutation('almanach_create_kin');
  const linkKin = useAlmanachMutation('almanach_link_kin');
  const setHolder = useAlmanachMutation('almanach_set_holder');

  const [name, setName] = useState('');
  const [genderId, setGenderId] = useState<number | null>(null);
  const [age, setAge] = useState('');
  const [status, setLife] = useState<Status>('alive');
  const [accurate, setAccurate] = useState(true);
  const [obituary, setObituary] = useState('');
  const [createFamily, setCreateFamily] = useState(false);
  const [addKin, setAddKin] = useState(false);
  const [kinName, setKinName] = useState('');
  const [kinLink, setKinLink] = useState<Link_>('child');
  const [unionKindId, setUnionKindId] = useState<number | null>(null);
  const [record, setRecord] = useState<'public' | 'secret'>('public');
  const [sheetId, setSheetId] = useState('');

  useEffect(() => {
    if (!doc) return;
    setName(doc.person.name);
    setGenderId(doc.person.gender_id);
    setAge(doc.person.age == null ? '' : String(doc.person.age));
    setLife(doc.person.status);
    setAccurate(doc.person.record_accurate);
    setObituary(doc.person.obituary);
  }, [doc]);
  useEffect(() => {
    const list = unionKinds?.results ?? [];
    if (unionKindId == null && list.length > 0) setUnionKindId(list[0].id);
  }, [unionKinds, unionKindId]);

  if (!doc) {
    return (
      <div className="almanach">
        <div className="wrap p-6 text-sm text-muted-foreground">Loading the person…</div>
      </div>
    );
  }
  const { person, family, kin, house, titles, sheet } = doc;
  const currentTier = NPC_TIERS.indexOf(person.tier as (typeof NPC_TIERS)[number]);

  const save = () => {
    const fields: Record<string, unknown> = { node_id: personId };
    if (!person.is_pc && name.trim() !== person.name) fields.name = name.trim();
    if (genderId !== person.gender_id) fields.gender_id = genderId;
    const ageValue = age.trim() === '' ? null : Number(age);
    if (ageValue !== person.age) fields.age = ageValue;
    if (Object.keys(fields).length > 1) editPerson.mutate(fields);
    if (
      status !== person.status ||
      accurate !== person.record_accurate ||
      obituary !== person.obituary
    ) {
      setStatus.mutate({
        node_id: personId,
        status,
        record_accurate: accurate,
        obituary,
      });
    }
  };

  const submitKin = async () => {
    if (!family || kinName.trim() === '') return;
    const made = await createKin.mutateAsync({ family_id: family.id, name: kinName.trim() });
    if (made.success === false) return;
    const otherId = (made.data as { kinsperson_id: number }).kinsperson_id;
    await linkKin.mutateAsync({
      node_id: personId,
      other_id: otherId,
      link: kinLink,
      is_public_record: record === 'public',
      ...(kinLink === 'spouse' && unionKindId != null ? { union_kind_id: unionKindId } : {}),
    });
    setKinName('');
    setAddKin(false);
  };

  const pickSpouse = (hit: SearchHit) =>
    linkKin.mutate({
      node_id: personId,
      other_id: hit.id,
      link: 'spouse',
      is_public_record: record === 'public',
      ...(unionKindId != null ? { union_kind_id: unionKindId } : {}),
    });

  const familyLink =
    family &&
    (family.organization_id != null ? houseUrl(family.organization_id) : familyUrl(family.id));

  const { rows, doors } = personRecordRail(doc);

  return (
    <div className="almanach">
      <div className="bar">
        <span className="crumb">
          <span>
            <Link to="/staff/almanach">Almanach</Link>
          </span>
          {family && <span>{family.name}</span>}
          <span>{person.display_name}</span>
        </span>
        <span className="right">
          <span className="status">{person.is_pc ? 'PC' : person.tier_display.label}</span>
          <span className="mode">staff</span>
        </span>
      </div>
      <div className="almanac">
        <PersonContents family={family} house={house} titles={titles} sheet={sheet} />
        <main className="chapter">
          <h3>
            {person.display_name}{' '}
            <span className="tier">
              {tierMark(person.tier)} <span className="gone">{statusMark(person.status)}</span>
            </span>
          </h3>
          <div className="row3">
            <div className="field">
              <label htmlFor="p-name">name</label>
              <input
                id="p-name"
                type="text"
                value={name}
                readOnly={person.is_pc}
                onChange={(e) => setName(e.target.value)}
              />
            </div>
            <div className="field">
              <label htmlFor="p-gender">gender</label>
              <select
                id="p-gender"
                value={genderId ?? ''}
                onChange={(e) => setGenderId(e.target.value === '' ? null : Number(e.target.value))}
              >
                <option value="">unset</option>
                {(genders ?? []).map((g) => (
                  <option key={g.id} value={g.id}>
                    {g.display_name}
                  </option>
                ))}
              </select>
            </div>
            <div className="field">
              <label htmlFor="p-age">age</label>
              <input
                id="p-age"
                type="number"
                value={age}
                onChange={(e) => setAge(e.target.value)}
              />
            </div>
          </div>
          <div className="row3">
            <div className="field">
              <span className="label">NPC tier</span>
              <div className="seg" role="group" aria-label="NPC tier">
                {NPC_TIERS.map((tier, i) => (
                  <button
                    key={tier}
                    type="button"
                    aria-pressed={!person.is_pc && i === currentTier}
                    disabled={person.is_pc || i <= currentTier}
                    onClick={() => promote.mutate({ node_id: personId, tier })}
                  >
                    {i}
                  </button>
                ))}
              </div>
            </div>
            <div className="field">
              <span className="label">status</span>
              <div className="seg" role="group" aria-label="status">
                {(['alive', 'rip', 'missing'] as Status[]).map((s) => (
                  <button
                    key={s}
                    type="button"
                    aria-pressed={status === s}
                    disabled={person.is_pc && s !== status && (s === 'rip' || status === 'rip')}
                    onClick={() => setLife(s)}
                  >
                    {STATUS_LABELS[s]}
                  </button>
                ))}
              </div>
            </div>
            <div className="field">
              <span className="label">public record</span>
              <label className="ck" htmlFor="p-accurate">
                <input
                  id="p-accurate"
                  type="checkbox"
                  checked={accurate}
                  onChange={(e) => setAccurate(e.target.checked)}
                />{' '}
                status accurate
              </label>
            </div>
          </div>
          <div className="field">
            <label htmlFor="p-obituary">obituary</label>
            <input
              id="p-obituary"
              type="text"
              value={obituary}
              onChange={(e) => setObituary(e.target.value)}
            />
          </div>

          <h4 className="sec">Family</h4>
          <div className="row2">
            <div className="field">
              <span className="label">family</span>
              {family ? (
                <div className="val">
                  <Link to={familyLink ?? '#'}>{family.name}</Link>
                  <span className="meta"> {family.kind}</span>
                </div>
              ) : (
                <div className="pick">
                  <button type="button" className="new" onClick={() => setCreateFamily(true)}>
                    Create Family for {person.display_name}
                  </button>
                </div>
              )}
            </div>
            <div className="field">
              <span className="label">joined as</span>
              <div className="val">{family?.basis || <span className="meta">none</span>}</div>
            </div>
          </div>
          {createFamily && (
            <CreateFamilyForm
              holder={{ id: person.id, name: person.display_name }}
              initialName={person.name.split(' ').pop() ?? ''}
              onCancel={() => setCreateFamily(false)}
              onCreated={() => setCreateFamily(false)}
            />
          )}

          <h4 className="sec">Kin</h4>
          <ul className="kin">
            {kin.map((k) => (
              <li key={`${k.relation}-${k.id}`}>
                <span className="nm">
                  <Link to={personUrl(k.id)}>{k.name}</Link>{' '}
                  <span className="gone">{statusMark(k.status)}</span>
                </span>
                <span className="rel">{k.relation}</span>
                <span className={k.is_appable ? 'st open' : 'st'}>
                  {k.is_appable ? 'appable' : tierMark(k.tier)}
                </span>
              </li>
            ))}
            <li>
              <span className="nm">
                <button
                  type="button"
                  className="add"
                  disabled={!family}
                  onClick={() => setAddKin((v) => !v)}
                >
                  Add kin
                </button>
              </span>
            </li>
          </ul>
          {addKin && family && (
            <div className="inline-new">
              <span className="label">Add kin</span>
              <div className="row3">
                <div className="field">
                  <label htmlFor="k-name">name</label>
                  <input
                    id="k-name"
                    type="text"
                    value={kinName}
                    onChange={(e) => setKinName(e.target.value)}
                  />
                </div>
                <div className="field">
                  <label htmlFor="k-link">link</label>
                  <select
                    id="k-link"
                    value={kinLink}
                    onChange={(e) => setKinLink(e.target.value as Link_)}
                  >
                    <option value="parent">parent</option>
                    <option value="child">child</option>
                    <option value="spouse">spouse</option>
                  </select>
                </div>
                <div className="field">
                  <label htmlFor="k-record">record</label>
                  <select
                    id="k-record"
                    value={record}
                    onChange={(e) => setRecord(e.target.value as 'public' | 'secret')}
                  >
                    <option value="public">Public</option>
                    <option value="secret">Secret</option>
                  </select>
                </div>
              </div>
              {kinLink === 'spouse' && (
                <div className="row2">
                  <div className="field">
                    <label htmlFor="k-union">union</label>
                    <select
                      id="k-union"
                      value={unionKindId ?? ''}
                      onChange={(e) =>
                        setUnionKindId(e.target.value === '' ? null : Number(e.target.value))
                      }
                    >
                      {(unionKinds?.results ?? []).map((u) => (
                        <option key={u.id} value={u.id}>
                          {u.name}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="field">
                    <span className="label">Add spouse</span>
                    <Picker
                      kind="person"
                      placeholder="Search people"
                      exclude={[personId]}
                      onPick={pickSpouse}
                    />
                  </div>
                </div>
              )}
              <div className="savebar">
                <button
                  type="button"
                  className="btn sm"
                  disabled={kinName.trim() === ''}
                  onClick={() => void submitKin()}
                >
                  Add
                </button>
                <button type="button" className="btn sm quiet" onClick={() => setAddKin(false)}>
                  Cancel
                </button>
              </div>
            </div>
          )}

          {house && (
            <>
              <h4 className="sec">{house.name}</h4>
              <div className="row3">
                <div className="field">
                  <span className="label">role</span>
                  <div className="val">{house.role || <span className="meta">none</span>}</div>
                </div>
                <div className="field">
                  <span className="label">rank</span>
                  <div className="val">{house.rank ?? <span className="meta">none</span>}</div>
                </div>
                <div className="field">
                  <span className="label">household post</span>
                  <div className="val">
                    {house.household_post || <span className="meta">none</span>}
                  </div>
                </div>
              </div>
            </>
          )}

          <h4 className="sec">Titles</h4>
          <div className="scroll">
            <table className="lad">
              <thead>
                <tr>
                  <th scope="col">title</th>
                  <th scope="col">realm</th>
                  <th scope="col">held as</th>
                  <th scope="col" className="n">
                    vassals
                  </th>
                </tr>
              </thead>
              <tbody>
                {titles.map((t) => (
                  <tr key={t.title_id}>
                    <td>
                      <Link to={titleUrl(t.title_id)}>{t.name}</Link>
                      {t.seat && <span className="meta"> seat: {t.seat}</span>}
                    </td>
                    <td>{t.realm}</td>
                    <td>holder, for {t.held_by}</td>
                    <td className="n">{t.vassals}</td>
                  </tr>
                ))}
                <tr>
                  <td colSpan={4}>
                    <Picker
                      kind="title"
                      placeholder="Add title"
                      ariaLabel="Add title"
                      onPick={(hit) => setHolder.mutate({ title_id: hit.id, node_id: personId })}
                    />
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <h4 className="sec">Sheet</h4>
          <div className="row3">
            <div className="field">
              <span className="label">appable</span>
              <div className="seg" role="group" aria-label="appable">
                <button
                  type="button"
                  aria-pressed={!sheet.is_appable}
                  disabled={sheet.sheet_id != null}
                  onClick={() => setAppable.mutate({ node_id: personId, appable: false })}
                >
                  No
                </button>
                <button
                  type="button"
                  aria-pressed={sheet.is_appable}
                  disabled={sheet.sheet_id != null}
                  onClick={() =>
                    setAppable.mutate({
                      node_id: personId,
                      appable: true,
                      age_min: sheet.age_min,
                      age_max: sheet.age_max,
                      allowed_gender_ids: sheet.allowed_gender_ids,
                      name_locked: sheet.name_locked,
                    })
                  }
                >
                  Yes
                </button>
              </div>
            </div>
            <div className="field">
              <span className="label">sheet</span>
              <div className="val">
                {sheet.sheet_id != null ? (
                  <Link to={`/characters/${sheet.sheet_id}`}>sheet {sheet.sheet_id}</Link>
                ) : (
                  <span className="meta">none</span>
                )}
              </div>
            </div>
            {sheet.sheet_id == null && !person.is_pc && (
              <div className="field">
                <span className="label">&nbsp;</span>
                <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                  <input
                    type="number"
                    aria-label="sheet id"
                    placeholder="sheet id"
                    value={sheetId}
                    onChange={(e) => setSheetId(e.target.value)}
                    style={{ width: '7rem' }}
                  />
                  <button
                    type="button"
                    className="btn sm quiet"
                    disabled={sheetId.trim() === ''}
                    onClick={() =>
                      attachSheet.mutate({ node_id: personId, sheet_id: Number(sheetId) })
                    }
                  >
                    Link sheet
                  </button>
                  <button
                    type="button"
                    className="btn sm quiet"
                    onClick={() => promote.mutate({ node_id: personId, tier: 'sheeted' })}
                  >
                    Create NPC sheet
                  </button>
                </div>
              </div>
            )}
          </div>

          <div className="savebar">
            <button type="button" className="btn" onClick={save}>
              Save
            </button>
          </div>
        </main>
        <RecordRail rows={rows} doors={doors} />
      </div>
    </div>
  );
}

function PersonContents({
  family,
  house,
  titles,
  sheet,
}: Pick<PersonDocument, 'family' | 'house' | 'titles' | 'sheet'>) {
  return (
    <aside className="contents">
      <ol>
        <li className="cur">Person</li>
        <li>
          Family<small>{family ? family.name : 'none'}</small>
        </li>
        <li>
          House<small>{house ? house.role || house.name : 'none'}</small>
        </li>
        <li>
          Titles<small>{titles.length}</small>
        </li>
        <li>
          Sheet<small>{sheet.sheet_id ? sheet.sheet_id : 'none'}</small>
        </li>
      </ol>
      <div className="mv">
        <span className="label">also in</span>
        <ol>
          <li>
            Roster<small>{sheet.is_appable ? 'appable' : 'not appable'}</small>
          </li>
          <li>
            Public tree<small>{family ? 'with the family' : 'none'}</small>
          </li>
        </ol>
      </div>
    </aside>
  );
}

function personRecordRail(doc: PersonDocument) {
  const { person, family, house, titles, sheet, memberships, record: counts } = doc;
  const familyLink =
    family &&
    (family.organization_id != null ? houseUrl(family.organization_id) : familyUrl(family.id));
  const rows: RecordRailRow[] = [
    {
      label: 'NPC tier',
      value: person.is_pc ? 'PC' : `${person.tier_display.number} · ${person.tier_display.label}`,
    },
    { label: 'status', value: statusMark(person.status) || 'Alive' },
    {
      label: 'family',
      value: family ? `${family.name}${family.basis ? `, ${family.basis}` : ''}` : 'none',
    },
    {
      label: 'house',
      value: house ? `${house.name}${house.role ? `, ${house.role}` : ''}` : 'none',
    },
    { label: 'holds', value: titles.map((t) => t.name).join(', ') || 'none' },
    { label: 'parents', value: counts.parents },
    { label: 'siblings', value: counts.siblings },
    { label: 'children', value: counts.children },
    { label: 'unions', value: counts.unions },
    { label: 'sheet', value: sheet.sheet_id ?? 'none' },
    { label: 'hidden truths', value: counts.hidden_truths },
  ];
  const doors: RecordRailDoor[] = [];
  if (family && familyLink) doors.push({ label: family.name, to: familyLink });
  if (house) doors.push({ label: `${house.name} organization`, to: orgUrl(house.org_id) });
  for (const t of titles) doors.push({ label: t.name, to: titleUrl(t.title_id) });
  if (family) doors.push({ label: 'Public tree', to: `/families/${family.id}` });
  for (const m of memberships) doors.push({ label: m.name, small: m.rank, to: orgUrl(m.org_id) });

  return { rows, doors };
}

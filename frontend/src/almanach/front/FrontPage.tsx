/**
 * The Almanach's front page (#4239): Noble, Crime, Commoner, each a roll with
 * a search of its own; one search over everything; Create Domain, Create
 * Family, Create Kin. The realm ladder behind the noble roll is the page
 * that was here before.
 */
import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import { useAlmanachMutation, useFront, useRealms, useSearch } from '../queries';
import type { SearchHit } from '../types';
import { CreateFamilyForm } from './CreateFamilyForm';
import { Picker } from '../shared/Picker';
import { familyUrl, houseUrl, personUrl, titleUrl } from '../shared/tier';
import '../almanach.css';

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

function hitUrl(hit: SearchHit): string {
  if (hit.kind === 'person') return personUrl(hit.id);
  if (hit.kind === 'family') return familyUrl(hit.id);
  if (hit.kind === 'organization') return houseUrl(hit.id);
  return titleUrl(hit.id);
}

function Roll({
  heading,
  q,
  onQ,
  rows,
  placeholder,
}: {
  heading: string;
  q: string;
  onQ: (v: string) => void;
  rows: Record<string, unknown>[] | undefined;
  placeholder: string;
}) {
  return (
    <section>
      <h4>{heading}</h4>
      <input
        type="search"
        className="rs"
        aria-label={`Search ${heading.toLowerCase()}`}
        placeholder={placeholder}
        value={q}
        onChange={(e) => onQ(e.target.value)}
      />
      <ul className="roll">
        {(rows ?? []).map((r) => {
          const id = r.id as number;
          const name = r.name as string;
          const kind = r.kind as string;
          let to: string | null = null;
          let meta = '';
          if (kind === 'realm') {
            to = `/staff/almanach/realms/${id}`;
            meta =
              (r.titles as number) > 0
                ? `${r.titles} titles · ${r.held} held · ${r.unclaimed} unclaimed`
                : 'nothing planted';
          } else if (kind === 'house') {
            to = houseUrl(id);
            meta = (r.sub as string) ?? '';
          } else if (kind === 'city') {
            meta = `${plural(r.families as number, 'family', 'families')} · ${plural(r.gangs as number, 'gang', 'gangs')} · ${plural(r.crew_slots as number, 'crew slot', 'crew slots')}`;
          } else if (kind === 'family' && 'on_record' in r) {
            to = familyUrl(id);
            meta = `${r.sub ? `${r.sub} · ` : ''}${r.on_record} on record${
              (r.appable as number) > 0 ? ` · ${r.appable} appable` : ''
            }`;
          } else if (kind === 'family') {
            to = houseUrl(id);
            meta = (r.sub as string) ?? '';
          }
          return (
            <li key={`${kind}-${id}`}>
              {to ? <Link to={to}>{name}</Link> : <span>{name}</span>}
              <span className="meta">{meta}</span>
            </li>
          );
        })}
        {rows && rows.length === 0 && (
          <li>
            <span className="meta">none</span>
          </li>
        )}
      </ul>
    </section>
  );
}

export function FrontPage() {
  const navigate = useNavigate();
  const [q, setQ] = useState('');
  const [nobleQ, setNobleQ] = useState('');
  const [crimeQ, setCrimeQ] = useState('');
  const [commonerQ, setCommonerQ] = useState('');
  const [open, setOpen] = useState<'family' | 'kin' | 'domain' | null>(null);
  const { data: all } = useFront('');
  const { data: noble } = useFront(nobleQ.trim());
  const { data: crime } = useFront(crimeQ.trim());
  const { data: commoner } = useFront(commonerQ.trim());
  const { data: hits } = useSearch(q);
  const { data: realms } = useRealms();
  const createKin = useAlmanachMutation('almanach_create_kin');
  const [kinName, setKinName] = useState('');
  const [kinFamily, setKinFamily] = useState<SearchHit | null>(null);

  const submitKin = async () => {
    if (!kinFamily || kinName.trim() === '') return;
    const result = await createKin.mutateAsync({ family_id: kinFamily.id, name: kinName.trim() });
    if (result.success !== false) {
      const data = result.data as { kinsperson_id: number };
      navigate(personUrl(data.kinsperson_id));
    }
  };

  return (
    <div className="almanach">
      <div className="bar">
        <span className="crumb">
          <span>Staff</span>
          <span>Almanach de Catenys</span>
        </span>
        <span className="right">
          <span className="mode">staff</span>
        </span>
      </div>
      <div className="front-bar">
        <input
          type="search"
          className="rs"
          aria-label="Search"
          placeholder="Search people, families, domains"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <div className="acts">
          <button
            type="button"
            className="btn quiet"
            onClick={() => setOpen(open === 'domain' ? null : 'domain')}
          >
            Create Domain
          </button>
          <button
            type="button"
            className="btn quiet"
            onClick={() => setOpen(open === 'family' ? null : 'family')}
          >
            Create Family
          </button>
          <button
            type="button"
            className="btn"
            onClick={() => setOpen(open === 'kin' ? null : 'kin')}
          >
            Create Kin
          </button>
        </div>
      </div>
      {q.trim().length >= 2 && (
        <ul className="roll" style={{ padding: '0.6rem 1.6rem 0' }} aria-label="Search results">
          {(hits ?? []).map((hit) => (
            <li key={`${hit.kind}-${hit.id}`}>
              <Link to={hitUrl(hit)}>{hit.name}</Link>
              <span className="meta">
                {hit.kind}
                {hit.sub ? ` · ${hit.sub}` : ''}
              </span>
            </li>
          ))}
          {hits && hits.length === 0 && (
            <li>
              <span className="meta">none found</span>
            </li>
          )}
        </ul>
      )}
      {open === 'domain' && (
        <div className="inline-new" style={{ margin: '1rem 1.6rem 0', maxWidth: '44rem' }}>
          <span className="label">Create Domain</span>
          <div className="field">
            <label htmlFor="front-realm">realm</label>
            <select
              id="front-realm"
              defaultValue=""
              onChange={(e) => {
                if (e.target.value !== '') navigate(`/staff/almanach/realms/${e.target.value}`);
              }}
            >
              <option value="">pick</option>
              {(realms?.results ?? []).map((r) => (
                <option key={r.id} value={r.id}>
                  {r.name}
                </option>
              ))}
            </select>
          </div>
        </div>
      )}
      {open === 'family' && (
        <div style={{ margin: '1rem 1.6rem 0', maxWidth: '44rem' }}>
          <CreateFamilyForm
            onCancel={() => setOpen(null)}
            onCreated={(data) =>
              navigate(data.org_id != null ? houseUrl(data.org_id) : familyUrl(data.family_id))
            }
          />
        </div>
      )}
      {open === 'kin' && (
        <div className="inline-new" style={{ margin: '1rem 1.6rem 0', maxWidth: '44rem' }}>
          <span className="label">Create Kin</span>
          <div className="row2">
            <div className="field">
              <label htmlFor="kin-name">name</label>
              <input
                id="kin-name"
                type="text"
                value={kinName}
                onChange={(e) => setKinName(e.target.value)}
              />
            </div>
            <div className="field">
              <span className="label">family</span>
              {kinFamily ? (
                <div className="val">
                  {kinFamily.name}{' '}
                  <button type="button" className="add" onClick={() => setKinFamily(null)}>
                    change
                  </button>
                </div>
              ) : (
                <Picker kind="family" placeholder="Search families" onPick={setKinFamily} />
              )}
            </div>
          </div>
          <div className="savebar">
            <button
              type="button"
              className="btn"
              disabled={!kinFamily || kinName.trim() === ''}
              onClick={() => void submitKin()}
            >
              Create
            </button>
            <button type="button" className="btn quiet" onClick={() => setOpen(null)}>
              Cancel
            </button>
          </div>
        </div>
      )}
      <div className="kinds">
        <Roll
          heading="Noble"
          q={nobleQ}
          onQ={setNobleQ}
          rows={(nobleQ.trim() ? noble : all)?.noble as Record<string, unknown>[] | undefined}
          placeholder="Search houses"
        />
        <Roll
          heading="Crime"
          q={crimeQ}
          onQ={setCrimeQ}
          rows={(crimeQ.trim() ? crime : all)?.crime as Record<string, unknown>[] | undefined}
          placeholder="Search families"
        />
        <Roll
          heading="Commoner"
          q={commonerQ}
          onQ={setCommonerQ}
          rows={
            (commonerQ.trim() ? commoner : all)?.commoner as Record<string, unknown>[] | undefined
          }
          placeholder="Search families"
        />
      </div>
    </div>
  );
}

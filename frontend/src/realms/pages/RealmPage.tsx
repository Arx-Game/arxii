/**
 * A realm's page at /realms/:slug (#3725, ADR-0285).
 *
 * Opens on the testament (the realm's pitch, authored as movements that each end on a
 * motto line), in the realm's own palette for the visit, with a rail above it that
 * jumps to the hub sections: Societies, Houses and organizations, Names spoken here
 * (two boards: renown and legend; names and the phrase the world speaks, never a
 * number), Characters (the roster filtered to the realm). Every hub section reads
 * rows kept for other reasons; the only authored thing here is the testament.
 */

import { useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { Skeleton } from '@/components/ui/skeleton';
import { CharacterAvatarLink, CharacterLink } from '@/components/character';
import { REALM_THEMES, useRealmTheme } from '@/components/realm-theme-provider';
import type { RealmTheme } from '@/components/realm-theme-provider';
import { useRealm, useRealmNotables, useRealmOrganizations, useRealmRoster } from '../queries';
import type { RankingRow, RealmDetail, RealmOrganization } from '../types';
import '../realm.css';

const SECTIONS = [
  { id: 'testament', label: 'Testament' },
  { id: 'societies', label: 'Societies' },
  { id: 'houses', label: 'Houses and organizations' },
  { id: 'names', label: 'Names spoken here' },
  { id: 'characters', label: 'Characters' },
] as const;

/** How many characters the page shows before handing off to the roster. */
const ROSTER_PREVIEW = 12;

function paragraphs(body: string): string[] {
  return body
    .split(/\n\s*\n/)
    .map((p) => p.trim())
    .filter(Boolean);
}

function Testament({ realm }: { realm: RealmDetail }) {
  let first = true;
  return (
    <div className="realm-testament">
      {realm.sections.map((section) => (
        <div key={section.sort_order}>
          {paragraphs(section.body).map((text, index) => {
            const dropcap = first;
            first = false;
            return (
              <p key={index} className={dropcap ? 'realm-dropcap' : undefined}>
                {text}
              </p>
            );
          })}
          {section.motto && <p className="realm-motto">{section.motto}</p>}
        </div>
      ))}
      {realm.sections.length === 0 && (
        <p className="realm-empty">This realm's testament has not been written yet.</p>
      )}
    </div>
  );
}

function Board({ title, rows }: { title: string; rows: RankingRow[] | undefined }) {
  return (
    <div className="realm-board">
      <h3>{title}</h3>
      {rows && rows.length > 0 ? (
        <ol>
          {rows.map((row, index) => (
            <li key={`${index}-${row.persona_name}`}>
              <i>{index + 1}</i>
              <span>{row.persona_name}</span>
              <em>{row.band_label}</em>
            </li>
          ))}
        </ol>
      ) : (
        <p className="realm-empty">No names are spoken here yet.</p>
      )}
    </div>
  );
}

function groupByKind(orgs: RealmOrganization[]): [string, RealmOrganization[]][] {
  const groups = new Map<string, RealmOrganization[]>();
  for (const org of orgs) {
    const kind = org.org_type_name || 'Organizations';
    groups.set(kind, [...(groups.get(kind) ?? []), org]);
  }
  return [...groups.entries()];
}

function useRailHighlight(): string {
  const [current, setCurrent] = useState<string>(SECTIONS[0].id);
  useEffect(() => {
    if (typeof IntersectionObserver === 'undefined') return undefined;
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries.filter((e) => e.isIntersecting);
        if (visible.length > 0) setCurrent(visible[0].target.id);
      },
      { rootMargin: '-20% 0px -70% 0px' }
    );
    for (const section of SECTIONS) {
      const el = document.getElementById(section.id);
      if (el) observer.observe(el);
    }
    return () => observer.disconnect();
  }, []);
  return current;
}

export function RealmPage() {
  const { slug } = useParams<{ slug: string }>();
  const { data: realm, isLoading, isError } = useRealm(slug);
  const { data: orgs } = useRealmOrganizations(slug);
  const { data: boards } = useRealmNotables(slug);
  const { data: roster } = useRealmRoster(slug);
  const { setForcedRealm } = useRealmTheme();
  const current = useRailHighlight();

  // The realm's palette for the visit, restored on leaving (as the landing page does).
  const theme = realm?.theme;
  useEffect(() => {
    if (theme && (REALM_THEMES as readonly string[]).includes(theme)) {
      setForcedRealm(theme as RealmTheme);
    }
    return () => setForcedRealm(undefined);
  }, [theme, setForcedRealm]);

  const grouped = useMemo(() => groupByKind(orgs ?? []), [orgs]);

  if (isLoading) {
    return (
      <main className="realm-page" aria-busy="true">
        <Skeleton className="h-10 w-1/3" />
        <Skeleton className="mt-4 h-4 w-2/3" />
      </main>
    );
  }
  if (isError || !realm) {
    return (
      <main className="realm-page">
        <p className="realm-empty">No realm by that name.</p>
        <p className="realm-more">
          <Link to="/realms">All realms</Link>
        </p>
      </main>
    );
  }

  const entries = roster?.results ?? [];
  const total = roster?.count ?? entries.length;

  return (
    <main className="realm-page">
      <header className="realm-head">
        {realm.starting_area?.crest_image ? (
          <img className="realm-crest" src={realm.starting_area.crest_image} alt="" />
        ) : (
          <div className="realm-crest" aria-hidden="true" />
        )}
        <div>
          <span className="realm-eyebrow">Realm</span>
          <h1>{realm.name}</h1>
          {realm.formal_name && <p className="realm-formal">{realm.formal_name}</p>}
          <p className="realm-threshold">“{realm.threshold_line}”</p>
        </div>
      </header>

      <nav className="realm-rail" aria-label="Sections of this realm">
        {SECTIONS.map((section) => (
          <a
            key={section.id}
            href={`#${section.id}`}
            className={current === section.id ? 'on' : undefined}
          >
            {section.label}
          </a>
        ))}
      </nav>

      <section id="testament" className="realm-leaf realm-section">
        <div>
          <Testament realm={realm} />
        </div>
        <aside>
          <span className="realm-note">
            <b>Begin here.</b>{' '}
            {realm.starting_area ? (
              <>
                {realm.starting_area.name} is the way into {realm.name}.{' '}
                <Link to="/#beginnings">See its Beginnings</Link> or{' '}
                <Link to="/characters/create">start a character</Link>.
              </>
            ) : (
              <>No starting area of {realm.name} is open right now.</>
            )}
          </span>
          <span className="realm-note">
            <b>Skip the testament.</b> <a href="#houses">Houses and organizations</a> ·{' '}
            <a href="#names">Names spoken here</a> · <a href="#characters">Characters</a>
          </span>
          <span className="realm-note">
            <Link to="/realms">All realms</Link>
          </span>
        </aside>
      </section>

      <section id="societies" className="realm-section">
        <h2>
          Societies <small>how the realm sees the world, and how it answers deeds</small>
        </h2>
        {realm.societies.length > 0 ? (
          <div className="realm-cards">
            {realm.societies.map((society) => (
              <div key={society.id} className="realm-card">
                <b>{society.name}</b>
                {society.enforcer_name && (
                  <span className="realm-sub">its enforcer: {society.enforcer_name}</span>
                )}
                {society.description && <p>{society.description}</p>}
              </div>
            ))}
          </div>
        ) : (
          <p className="realm-empty">No societies are recorded for this realm yet.</p>
        )}
      </section>

      <section id="houses" className="realm-section">
        <h2>
          Houses and organizations <small>grouped by kind</small>
        </h2>
        {grouped.length > 0 ? (
          grouped.map(([kind, rows]) => (
            <ul key={kind} className="realm-orgs" aria-label={kind}>
              {rows.map((org) => (
                <li key={org.id}>
                  <div>
                    <Link to={`/orgs/${org.id}`}>{org.name}</Link>
                    {(org.words || org.sigil_description) && (
                      <>
                        <br />
                        {org.words && <span className="realm-words">“{org.words}”</span>}
                        {org.words && org.sigil_description && ' · '}
                        {org.sigil_description && <span>{org.sigil_description}</span>}
                      </>
                    )}
                  </div>
                  <span className="realm-kind">{kind}</span>
                </li>
              ))}
            </ul>
          ))
        ) : (
          <p className="realm-empty">No houses or organizations are recorded here yet.</p>
        )}
      </section>

      <section id="names" className="realm-section">
        <h2>
          Names spoken here <small>the realm's herald; names and the phrase the world speaks</small>
        </h2>
        <div className="realm-boards">
          <Board title="By renown" rows={boards?.renown} />
          <Board title="By legend" rows={boards?.legend} />
        </div>
      </section>

      <section id="characters" className="realm-section">
        <h2>
          Characters <small>of {realm.name}, on the roster</small>
        </h2>
        {entries.length > 0 ? (
          <>
            <div className="realm-roster">
              {entries.slice(0, ROSTER_PREVIEW).map((entry) => (
                <div key={entry.id} className="realm-pc">
                  <CharacterAvatarLink
                    id={entry.id}
                    name={entry.character.name}
                    avatarUrl={entry.profile_picture?.media.cloudinary_url}
                    className="h-10 w-10"
                    fallback=""
                  />
                  <div>
                    <CharacterLink id={entry.id}>{entry.character.name}</CharacterLink>
                    {entry.character.char_class && <span>{entry.character.char_class}</span>}
                  </div>
                </div>
              ))}
            </div>
            <p className="realm-more">
              <Link to={`/roster?realm=${realm.slug}`}>
                All {total} characters of {realm.name} on the roster{' '}
                <span aria-hidden="true">→</span>
              </Link>
            </p>
          </>
        ) : (
          <p className="realm-empty">No characters of {realm.name} are on the roster yet.</p>
        )}
      </section>
    </main>
  );
}

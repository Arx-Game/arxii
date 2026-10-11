/**
 * A family's page when it has no organization (#4239): an orphan's dozen NPC
 * relatives, a background family. Its people, Add kin, its appable kin, and
 * Create organization for the day it takes standing. A family that has an
 * organization is its house document.
 */
import { useEffect, useState } from 'react';
import { Link, Navigate } from 'react-router-dom';

import { useAlmanachMutation, useFamilyDocument, useTemplates } from '../queries';
import { RecordRail, type RecordRailRow } from '../document/RecordRail';
import { Openings } from '../shared/chapters';
import { houseUrl, personUrl, statusFromFlags, statusMark, tierMark } from '../shared/tier';
import '../almanach.css';

export function StaffFamilyPage({ familyId }: { familyId: number }) {
  const { data: doc } = useFamilyDocument(familyId);
  const createKin = useAlmanachMutation('almanach_create_kin');
  const foundOrg = useAlmanachMutation('almanach_found_organization');
  const [kinName, setKinName] = useState('');
  const [templateId, setTemplateId] = useState<number | null>(null);
  const [founding, setFounding] = useState(false);
  const { data: templates } = useTemplates(doc?.family.realm_id ?? null, null);

  useEffect(() => {
    const list = templates?.results ?? [];
    if (templateId == null && list.length > 0) setTemplateId(list[0].id);
  }, [templates, templateId]);

  if (!doc) {
    return (
      <div className="almanach">
        <div className="wrap p-6 text-sm text-muted-foreground">Loading the family…</div>
      </div>
    );
  }
  if (doc.organization_id != null) {
    return <Navigate to={houseUrl(doc.organization_id)} replace />;
  }
  const { family, tree, openings } = doc;
  const rows: RecordRailRow[] = [
    { label: 'type', value: family.kind || 'none' },
    { label: 'realm', value: family.realm || 'none' },
    { label: 'on record', value: tree.nodes.length },
    { label: 'appable', value: openings.appable.length },
    { label: 'organization', value: 'none' },
  ];

  return (
    <div className="almanach">
      <div className="bar">
        <span className="crumb">
          <span>Almanach</span>
          {family.realm && <span>{family.realm}</span>}
          <span>{family.name}</span>
        </span>
        <span className="right">
          <span className="status">{family.kind || 'family'}</span>
          <span className="mode">staff</span>
        </span>
      </div>
      <div className="almanac">
        <aside className="contents">
          <ol>
            <li className="cur">
              Family<small>{tree.nodes.length} on record</small>
            </li>
            <li>
              Openings<small>{openings.appable.length}</small>
            </li>
          </ol>
        </aside>
        <main className="chapter">
          <h3>
            {family.name} <span className="tier">{family.kind}</span>
          </h3>
          <ul className="kin">
            {tree.nodes.map((n) => (
              <li key={n.id}>
                <span className="nm">
                  <Link to={personUrl(n.id)}>{n.name}</Link>{' '}
                  <span className="gone">
                    {statusMark(statusFromFlags(n.is_deceased, n.is_missing ?? false))}
                  </span>
                </span>
                <span className="rel">{n.gender}</span>
                <span className={n.is_appable ? 'st open' : 'st'}>
                  {n.is_appable ? 'appable' : tierMark(n.tier)}
                </span>
              </li>
            ))}
            <li>
              <span className="nm">
                <input
                  type="text"
                  aria-label="Add kin"
                  placeholder="Add kin"
                  value={kinName}
                  onChange={(e) => setKinName(e.target.value)}
                />
              </span>
              <span />
              <button
                type="button"
                className="add"
                disabled={kinName.trim() === ''}
                onClick={() => {
                  createKin.mutate({ family_id: familyId, name: kinName.trim() });
                  setKinName('');
                }}
              >
                Add kin
              </button>
            </li>
          </ul>

          <Openings openings={openings} />

          <h4 className="sec">Organization</h4>
          {founding ? (
            <div className="inline-new">
              <span className="label">Create organization</span>
              <div className="field">
                <label htmlFor="fo-template">template</label>
                <select
                  id="fo-template"
                  value={templateId ?? ''}
                  onChange={(e) =>
                    setTemplateId(e.target.value === '' ? null : Number(e.target.value))
                  }
                >
                  {(templates?.results ?? []).map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.name}
                    </option>
                  ))}
                  {(templates?.results ?? []).length === 0 && (
                    <option value="">none for this realm</option>
                  )}
                </select>
              </div>
              <div className="savebar">
                <button
                  type="button"
                  className="btn sm"
                  disabled={templateId == null}
                  onClick={() => foundOrg.mutate({ family_id: familyId, template_id: templateId })}
                >
                  Create
                </button>
                <button type="button" className="btn sm quiet" onClick={() => setFounding(false)}>
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <div className="pick">
              <span className="meta">none</span>
              <button type="button" className="new" onClick={() => setFounding(true)}>
                Create organization
              </button>
            </div>
          )}
        </main>
        <RecordRail rows={rows} />
      </div>
    </div>
  );
}

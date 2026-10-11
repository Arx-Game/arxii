/**
 * Create Family (#4239): family type, name, realm, and the holding block.
 * A noble house carries its holding by default: Create plants a domain and
 * title under a rung and the house (and the chosen person) hold it; Vacant
 * title takes an unclaimed rung; None yet makes the family alone. A family
 * type that does not style as a house, with None yet, makes a Family row
 * and no organization. Copy is fragments; no explanation beside a control.
 */
import { useEffect, useState } from 'react';

import {
  useAlmanachMutation,
  useFamilyKinds,
  useRealmTitles,
  useRealms,
  useTemplates,
  useVacantTitles,
} from '../queries';

export type Holding = 'create' | 'vacant' | 'none';

const TITLE_TIERS = ['kingdom', 'duchy', 'march', 'county', 'barony'] as const;

const HOLDING_LABELS: Record<Holding, string> = {
  create: 'Create',
  vacant: 'Vacant title',
  none: 'None yet',
};

export interface CreateFamilyFormProps {
  /** Preselects the realm; the Create Family for <name> case passes the person's realm. */
  realmId?: number | null;
  /** The person the new house's title is held by, in person. */
  holder?: { id: number; name: string } | null;
  /** Add vassal house: the vacant title the new house takes, fixed. */
  vacantTitle?: { title_id: number; name: string; realm_id: number } | null;
  /** The rung a created domain nests under, fixed (the house's own title). */
  parentTitle?: { title_id: number; name: string; realm_id: number } | null;
  initialName?: string;
  onCreated?: (data: { family_id: number; org_id: number | null; title_id: number | null }) => void;
  onCancel?: () => void;
}

export function CreateFamilyForm({
  realmId,
  holder,
  vacantTitle,
  parentTitle,
  initialName = '',
  onCreated,
  onCancel,
}: CreateFamilyFormProps) {
  const { data: kinds } = useFamilyKinds();
  const { data: realms } = useRealms();
  const [kindId, setKindId] = useState<number | null>(null);
  const [name, setName] = useState(initialName);
  const [realm, setRealm] = useState<number | null>(
    realmId ?? vacantTitle?.realm_id ?? parentTitle?.realm_id ?? null
  );
  const [templateId, setTemplateId] = useState<number | null>(null);
  const [holding, setHolding] = useState<Holding>(vacantTitle ? 'vacant' : 'none');
  const [titleTier, setTitleTier] = useState<string>('county');
  const [titleName, setTitleName] = useState('');
  const [parentId, setParentId] = useState<number | null>(parentTitle?.title_id ?? null);
  const [vacantId, setVacantId] = useState<number | null>(vacantTitle?.title_id ?? null);

  const kind = (kinds?.results ?? []).find((k) => k.id === kindId) ?? null;
  const stylesAsHouse = kind?.styles_as_house ?? false;
  const needsOrg = stylesAsHouse || holding !== 'none';
  const { data: templates } = useTemplates(needsOrg ? realm : null, kindId);
  const { data: titles } = useRealmTitles(holding === 'create' && !parentTitle ? realm : null);
  const { data: vacant } = useVacantTitles(holding === 'vacant' && !vacantTitle ? realm : null);
  const create = useAlmanachMutation('almanach_create_family');

  useEffect(() => {
    if (kinds && kindId == null && kinds.results.length > 0) setKindId(kinds.results[0].id);
  }, [kinds, kindId]);
  useEffect(() => {
    if (realm == null && realms && realms.results.length > 0) setRealm(realms.results[0].id);
  }, [realms, realm]);
  useEffect(() => {
    if (stylesAsHouse && holding === 'none' && !vacantTitle) setHolding('create');
  }, [stylesAsHouse, holding, vacantTitle]);
  useEffect(() => {
    const list = templates?.results ?? [];
    if (needsOrg && list.length > 0 && !list.some((t) => t.id === templateId)) {
      setTemplateId(list[0].id);
    }
  }, [templates, needsOrg, templateId]);

  const canSubmit =
    name.trim() !== '' &&
    kindId != null &&
    (!needsOrg || templateId != null) &&
    (holding !== 'create' || titleName.trim() !== '') &&
    (holding !== 'vacant' || vacantId != null);

  const submit = async () => {
    if (!canSubmit || kindId == null) return;
    const kwargs: Record<string, unknown> = {
      kind_id: kindId,
      name: name.trim(),
      realm_id: realm,
      holding,
    };
    if (needsOrg) kwargs.template_id = templateId;
    if (holding === 'create') {
      kwargs.title_tier = titleTier;
      kwargs.title_name = titleName.trim();
      if (parentId != null) kwargs.parent_title_id = parentId;
    }
    if (holding === 'vacant') kwargs.parent_title_id = vacantId;
    if (holder && holding !== 'none') kwargs.holder_id = holder.id;
    const result = await create.mutateAsync(kwargs);
    if (result.success !== false && onCreated) {
      onCreated(
        result.data as { family_id: number; org_id: number | null; title_id: number | null }
      );
    }
  };

  const formTitle = holder ? `Create Family for ${holder.name}` : 'Create Family';

  return (
    <div className="inline-new" role="form" aria-label={formTitle}>
      <span className="label">{formTitle}</span>
      <div className="row3">
        <div className="field">
          <label htmlFor="cf-kind">family type</label>
          <select
            id="cf-kind"
            value={kindId ?? ''}
            onChange={(e) => setKindId(e.target.value === '' ? null : Number(e.target.value))}
          >
            {(kinds?.results ?? []).map((k) => (
              <option key={k.id} value={k.id}>
                {k.name}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="cf-name">name</label>
          <input id="cf-name" type="text" value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="cf-realm">realm</label>
          <select
            id="cf-realm"
            value={realm ?? ''}
            disabled={realmId != null || !!vacantTitle || !!parentTitle}
            onChange={(e) => setRealm(e.target.value === '' ? null : Number(e.target.value))}
          >
            {(realms?.results ?? []).map((r) => (
              <option key={r.id} value={r.id}>
                {r.name}
              </option>
            ))}
          </select>
        </div>
      </div>
      {needsOrg && (
        <div className="field">
          <label htmlFor="cf-template">template</label>
          <select
            id="cf-template"
            value={templateId ?? ''}
            onChange={(e) => setTemplateId(e.target.value === '' ? null : Number(e.target.value))}
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
      )}
      <div className="row3">
        <div className="field">
          <span className="label">holding</span>
          <div className="seg" role="group" aria-label="holding">
            {(['create', 'vacant', 'none'] as Holding[]).map((h) => (
              <button
                key={h}
                type="button"
                aria-pressed={holding === h}
                disabled={!!vacantTitle && h !== 'vacant'}
                onClick={() => setHolding(h)}
              >
                {HOLDING_LABELS[h]}
              </button>
            ))}
          </div>
        </div>
        {holding === 'create' && (
          <>
            <div className="field">
              <label htmlFor="cf-tier">title</label>
              <select id="cf-tier" value={titleTier} onChange={(e) => setTitleTier(e.target.value)}>
                {TITLE_TIERS.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </div>
            <div className="field">
              <label htmlFor="cf-title-name">name</label>
              <input
                id="cf-title-name"
                type="text"
                value={titleName}
                onChange={(e) => setTitleName(e.target.value)}
              />
            </div>
          </>
        )}
        {holding === 'vacant' && (
          <div className="field">
            <label htmlFor="cf-vacant">title</label>
            {vacantTitle ? (
              <div className="val">{vacantTitle.name || 'unnamed'}</div>
            ) : (
              <select
                id="cf-vacant"
                value={vacantId ?? ''}
                onChange={(e) => setVacantId(e.target.value === '' ? null : Number(e.target.value))}
              >
                <option value="">pick</option>
                {(vacant?.results ?? []).map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name || `unnamed ${t.tier}`}
                  </option>
                ))}
              </select>
            )}
          </div>
        )}
      </div>
      {holding === 'create' && (
        <div className="row3">
          <div className="field">
            <label htmlFor="cf-under">under</label>
            {parentTitle ? (
              <div className="val">{parentTitle.name}</div>
            ) : (
              <select
                id="cf-under"
                value={parentId ?? ''}
                onChange={(e) => setParentId(e.target.value === '' ? null : Number(e.target.value))}
              >
                <option value="">the realm</option>
                {(titles?.results ?? [])
                  .filter((t) => t.name)
                  .map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.name}
                    </option>
                  ))}
              </select>
            )}
          </div>
          {holder && (
            <div className="field">
              <span className="label">held by</span>
              <div className="val">{holder.name}</div>
            </div>
          )}
        </div>
      )}
      <div className="savebar">
        <button
          type="button"
          className="btn"
          aria-label={formTitle}
          disabled={!canSubmit}
          onClick={() => void submit()}
        >
          Create
        </button>
        {onCancel && (
          <button type="button" className="btn quiet" onClick={onCancel}>
            Cancel
          </button>
        )}
      </div>
    </div>
  );
}

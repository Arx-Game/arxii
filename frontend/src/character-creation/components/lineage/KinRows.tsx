/**
 * The people seated beside the parents (#4395): a twin, a spouse, children, and since
 * #4870 a betrothed. Each row is a name, a gender and a fate for its kind (a twin's may be
 * left unsaid); the whole list is sent on every change (`draft_data.kin_rows`), and
 * finalize seats them in the kinship graph.
 */

import { useGenders, useUpdateDraft } from '../../queries';
import { ChoiceRow } from '../../folio';
import {
  BETROTHED_FATES,
  CHILD_FATES,
  SPOUSE_FATES,
  TWIN_FATES,
  type CGExplanations,
  type CharacterDraft,
  type KinRow,
  type KinRowKind,
} from '../../types';

interface Props {
  draft: CharacterDraft;
  copy: CGExplanations | undefined;
}

const KIND_LABELS: Record<KinRowKind, string> = {
  twin: 'A twin',
  spouse: 'A spouse',
  child: 'A child',
  betrothed: 'A betrothed',
};

/** Each kind's fates and the one a fresh row starts with. */
const FATES: Record<KinRowKind, { options: { value: string; label: string }[]; fresh: string }> = {
  twin: { options: TWIN_FATES, fresh: 'alive' },
  spouse: { options: SPOUSE_FATES, fresh: 'alive' },
  child: { options: CHILD_FATES, fresh: 'raised' },
  betrothed: { options: BETROTHED_FATES, fresh: 'promised' },
};

function freshRow(kind: KinRowKind): KinRow {
  return { kind, name: '', gender_id: null, fate: FATES[kind].fresh as KinRow['fate'] };
}

export function KinRows({ draft, copy }: Props) {
  const updateDraft = useUpdateDraft();
  const { data: genders } = useGenders();
  const rows: KinRow[] = draft.draft_data.kin_rows ?? [];
  const heading = copy?.kin_rows_heading ?? 'Kin';

  const save = (next: KinRow[]) =>
    updateDraft.mutate({ draftId: draft.id, data: { draft_data: { kin_rows: next } } });
  const add = (kind: KinRowKind) => save([...rows, freshRow(kind)]);
  const patch = (index: number, change: Partial<KinRow>) =>
    save(rows.map((row, i) => (i === index ? { ...row, ...change } : row)));
  const remove = (index: number) => save(rows.filter((_, i) => i !== index));
  const hasTwin = rows.some((row) => row.kind === 'twin');
  const genderOptions = (genders ?? []).map((g) => ({ value: g.id, label: g.display_name }));

  return (
    <section className="kin" aria-label={heading}>
      <h3 className="section-h">{heading}</h3>
      {rows.length > 0 && (
        <ul className="kin-rows">
          {rows.map((row, index) => (
            <li key={index} className="kin-row" aria-label={KIND_LABELS[row.kind]}>
              <span className="kin-kind">{KIND_LABELS[row.kind]}</span>
              <div className="kin-fields">
                <div className="field">
                  <label htmlFor={`kin-${index}-name`}>{copy?.kin_name_label ?? 'Name'}</label>
                  <input
                    id={`kin-${index}-name`}
                    type="text"
                    maxLength={100}
                    defaultValue={row.name}
                    onBlur={(e) => {
                      if (e.target.value !== row.name) patch(index, { name: e.target.value });
                    }}
                  />
                </div>
                <ChoiceRow
                  label={copy?.kin_gender_label ?? 'Gender'}
                  options={genderOptions}
                  value={row.gender_id}
                  onChange={(id) => patch(index, { gender_id: id })}
                />
                <ChoiceRow<string>
                  label={copy?.kin_fate_label ?? 'Fate'}
                  options={FATES[row.kind].options}
                  value={row.fate || null}
                  onChange={(fate) => {
                    if (fate !== null) patch(index, { fate: fate as KinRow['fate'] });
                  }}
                />
              </div>
              <button
                type="button"
                className="btn-quiet"
                aria-label={`Remove: ${KIND_LABELS[row.kind]}`}
                onClick={() => remove(index)}
              >
                {copy?.kin_remove_word ?? 'Remove'}
              </button>
            </li>
          ))}
        </ul>
      )}
      <div className="kin-add" role="group" aria-label={copy?.kin_add_word ?? 'Add'}>
        {!hasTwin && (
          <button type="button" onClick={() => add('twin')}>
            {KIND_LABELS.twin}
          </button>
        )}
        <button type="button" onClick={() => add('spouse')}>
          {KIND_LABELS.spouse}
        </button>
        <button type="button" onClick={() => add('child')}>
          {KIND_LABELS.child}
        </button>
        <button type="button" onClick={() => add('betrothed')}>
          {KIND_LABELS.betrothed}
        </button>
      </div>
    </section>
  );
}

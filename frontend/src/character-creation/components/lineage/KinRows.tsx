/**
 * The people seated beside the parents (#4395): a twin, a spouse, children. Each row
 * is a name, a gender and, for a spouse or a child, a fate; the whole list is sent on
 * every change (`draft_data.kin_rows`), and finalize seats them in the kinship graph.
 */

import { useGenders, useUpdateDraft } from '../../queries';
import { ChoiceRow } from '../../folio';
import {
  CHILD_FATES,
  SPOUSE_FATES,
  type CGExplanations,
  type CharacterDraft,
  type ChildFate,
  type KinRow,
  type KinRowKind,
  type SpouseFate,
} from '../../types';

interface Props {
  draft: CharacterDraft;
  copy: CGExplanations | undefined;
}

const KIND_LABELS: Record<KinRowKind, string> = {
  twin: 'A twin',
  spouse: 'A spouse',
  child: 'A child',
};

function freshRow(kind: KinRowKind): KinRow {
  if (kind === 'spouse') return { kind, name: '', gender_id: null, fate: 'alive' };
  if (kind === 'child') return { kind, name: '', gender_id: null, fate: 'raised' };
  return { kind, name: '', gender_id: null, fate: '' };
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
                {row.kind === 'spouse' && (
                  <ChoiceRow<SpouseFate>
                    label={copy?.kin_fate_label ?? 'Fate'}
                    options={SPOUSE_FATES}
                    value={(row.fate as SpouseFate) || null}
                    onChange={(fate) => {
                      if (fate !== null) patch(index, { fate });
                    }}
                  />
                )}
                {row.kind === 'child' && (
                  <ChoiceRow<ChildFate>
                    label={copy?.kin_fate_label ?? 'Fate'}
                    options={CHILD_FATES}
                    value={(row.fate as ChildFate) || null}
                    onChange={(fate) => {
                      if (fate !== null) patch(index, { fate });
                    }}
                  />
                )}
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
      </div>
    </section>
  );
}

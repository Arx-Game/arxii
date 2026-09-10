/**
 * MarkingsEditor (#2985, folio #3630) — CG appearance-stage authoring for body
 * markings.
 *
 * Tattoos, scars, brands, birthmarks, runes: each a row on the draft
 * (`/api/character-creation/draft-markings/`), materialized onto the
 * character's true form at finalization. Optional — no stage validation
 * reads these. Self-contained CRUD (react-query) rather than riding the
 * draft PATCH, since rows are structured records, not draft_data blobs.
 *
 * A marking is a feature (#3739), so each entry carries `FeatureDistinctions`:
 * its name and description stay free, and the point buys only the three
 * presence axes. That is the one difference from a trait row, where the same
 * point also opens the palette and the description.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import {
  createDraftMarking,
  deleteDraftMarking,
  listDraftMarkings,
  type DraftMarkingCreate,
} from '../api';
import { ChoiceRow, Entry, EntryList, Field } from '../folio';
import { FeatureDistinctions } from './offers/FeatureDistinctions';
import type { CharacterDraft } from '../types';

const MARKING_KINDS = [
  { value: 'tattoo', label: 'Tattoo' },
  { value: 'scar', label: 'Scar' },
  { value: 'brand', label: 'Brand' },
  { value: 'birthmark', label: 'Birthmark' },
  { value: 'rune', label: 'Rune' },
];

const BODY_REGIONS = [
  { value: 'head', label: 'Head' },
  { value: 'face', label: 'Face' },
  { value: 'neck', label: 'Neck' },
  { value: 'shoulders', label: 'Shoulders' },
  { value: 'torso', label: 'Torso' },
  { value: 'back', label: 'Back' },
  { value: 'waist', label: 'Waist' },
  { value: 'left_arm', label: 'Left Arm' },
  { value: 'right_arm', label: 'Right Arm' },
  { value: 'left_hand', label: 'Left Hand' },
  { value: 'right_hand', label: 'Right Hand' },
  { value: 'left_leg', label: 'Left Leg' },
  { value: 'right_leg', label: 'Right Leg' },
  { value: 'feet', label: 'Feet' },
];

const EMPTY_FORM: DraftMarkingCreate = {
  body_region: 'torso',
  kind: 'tattoo',
  name: '',
  description: '',
};

const MARKINGS_QUERY_KEY = ['draft-markings'] as const;

interface MarkingsEditorProps {
  /**
   * The draft, when the caller has it (#3739): each marking then offers the
   * per-feature rows. Omitted by any caller that only needs the CRUD list.
   */
  draft?: CharacterDraft;
  markingUnlockLabel?: string;
  markingUnlockWhy?: string;
  perTierWord?: string;
}

export function MarkingsEditor({
  draft,
  markingUnlockLabel,
  markingUnlockWhy,
  perTierWord,
}: MarkingsEditorProps = {}) {
  const queryClient = useQueryClient();
  const { data: markings = [] } = useQuery({
    queryKey: MARKINGS_QUERY_KEY,
    queryFn: listDraftMarkings,
  });
  const [form, setForm] = useState<DraftMarkingCreate>(EMPTY_FORM);

  const invalidate = () => queryClient.invalidateQueries({ queryKey: MARKINGS_QUERY_KEY });
  const addMutation = useMutation({
    mutationFn: createDraftMarking,
    onSuccess: () => {
      setForm(EMPTY_FORM);
      void invalidate();
    },
  });
  const removeMutation = useMutation({
    mutationFn: deleteDraftMarking,
    onSuccess: () => void invalidate(),
  });

  // The disabled door says why (accessibility floor, #3630). Only the name is
  // required: kind and region always carry a default, and the description is
  // optional.
  let addTitle: string | undefined;
  if (!form.name.trim()) {
    addTitle = 'A name is required';
  } else if (addMutation.isPending) {
    addTitle = 'Saving';
  }

  const regionLabel = (value: string) =>
    BODY_REGIONS.find((r) => r.value === value)?.label ?? value;
  const kindLabel = (value: string) => MARKING_KINDS.find((k) => k.value === value)?.label ?? value;

  return (
    <>
      {markings.length > 0 && (
        <EntryList label="Markings">
          {markings.map((marking) => (
            <Entry
              key={marking.id}
              name={marking.name}
              tag={`${kindLabel(marking.kind)} · ${regionLabel(marking.body_region)}`}
              chosen={false}
              open
            >
              <p>{marking.description}</p>
              {draft && (
                <FeatureDistinctions
                  draft={draft}
                  feature={{ feature_marking: marking.id }}
                  featureLabel={marking.name}
                  unlockLabel={markingUnlockLabel}
                  unlockWhy={markingUnlockWhy}
                  perTierWord={perTierWord}
                />
              )}
              <div className="entry-act">
                <button
                  type="button"
                  className="btn-quiet"
                  onClick={() => removeMutation.mutate(marking.id)}
                  disabled={removeMutation.isPending}
                >
                  Remove
                </button>
              </div>
            </Entry>
          ))}
        </EntryList>
      )}

      <h3 className="section-h">Add a marking</h3>
      <Field id="mk-name" label="Name">
        <input
          id="mk-name"
          type="text"
          value={form.name}
          maxLength={100}
          onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
        />
      </Field>
      <ChoiceRow
        label="Kind"
        options={MARKING_KINDS}
        value={form.kind}
        onChange={(kind) => kind && setForm((f) => ({ ...f, kind }))}
      />
      <ChoiceRow
        label="Region"
        options={BODY_REGIONS}
        value={form.body_region}
        onChange={(body_region) => body_region && setForm((f) => ({ ...f, body_region }))}
      />
      <Field id="mk-desc" label="Description">
        <textarea
          id="mk-desc"
          rows={2}
          value={form.description}
          onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
        />
      </Field>
      <p className="ledger-line">
        <button
          type="button"
          className="btn-small"
          disabled={!form.name.trim() || addMutation.isPending}
          title={addTitle}
          onClick={() => addMutation.mutate({ ...form, name: form.name.trim() })}
        >
          Add marking
        </button>
      </p>
    </>
  );
}

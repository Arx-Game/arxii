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
 * A marking is a feature (#3739), so each entry carries `FeatureDistinctions`,
 * the qualities line. Its name and description are free either way; on a trait
 * a quality also opens the palette and the description.
 *
 * The form asks for the name, the kind and the region on one line, the last two
 * as dropdowns (#5241, owner ruling 2026-11-21). They were two rows of buttons,
 * five kinds directly above fourteen regions, and read as one block.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import {
  createDraftMarking,
  deleteDraftMarking,
  listDraftMarkings,
  type DraftMarkingCreate,
} from '../api';
import { distinctionKeys } from '@/hooks/useDistinctions';
import { Entry, EntryList, Field } from '../folio';
import { characterCreationKeys } from '../queries';
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
   * qualities line. Omitted by any caller that only needs the CRUD list.
   */
  draft?: CharacterDraft;
}

export function MarkingsEditor({ draft }: MarkingsEditorProps = {}) {
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
    onSuccess: () => {
      void invalidate();
      // The server drops every quality held on the marking in the same request and
      // refunds its points (#3739), so the picks and every total change with it. Left
      // with the old list, the page kept counting the removed marking's points and
      // sent its pick again with the next quality clicked, which the server refuses.
      if (!draft) return;
      void queryClient.invalidateQueries({
        queryKey: distinctionKeys.draftDistinctions(draft.id),
      });
      void queryClient.invalidateQueries({ queryKey: characterCreationKeys.draft() });
      void queryClient.invalidateQueries({
        queryKey: characterCreationKeys.draftCGPoints(draft.id),
      });
    },
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
      <div className="field-row marking-row">
        <Field id="mk-name" label="Name">
          <input
            id="mk-name"
            type="text"
            value={form.name}
            maxLength={100}
            onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
          />
        </Field>
        <Field id="mk-kind" label="Kind">
          <select
            id="mk-kind"
            value={form.kind}
            onChange={(e) => setForm((f) => ({ ...f, kind: e.target.value }))}
          >
            {MARKING_KINDS.map((kind) => (
              <option key={kind.value} value={kind.value}>
                {kind.label}
              </option>
            ))}
          </select>
        </Field>
        <Field id="mk-region" label="Region">
          <select
            id="mk-region"
            value={form.body_region}
            onChange={(e) => setForm((f) => ({ ...f, body_region: e.target.value }))}
          >
            {BODY_REGIONS.map((region) => (
              <option key={region.value} value={region.value}>
                {region.label}
              </option>
            ))}
          </select>
        </Field>
      </div>
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

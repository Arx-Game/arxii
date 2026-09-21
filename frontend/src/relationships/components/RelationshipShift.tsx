/**
 * Relationship Shift (#3957) — one label becoming another.
 *
 * Not an edit: the old row ends and a new one begins remembering it, so a tie that went
 * from Enemy to Lover still says so a year later. That is why there is no Delete
 * anywhere near this block, and why the note the player may leave rides the NEW row.
 */

import { useState } from 'react';

import { Eyebrow, Ledger, QuietDoor } from '@/character_sheets/components/sheet/primitives';
import { useRelationshipTypes, useShiftLabel } from '@/relationships/queries';
import type { TieLabel } from '../api';
import { FAMILIES } from './TypePicker';

export interface RelationshipShiftProps {
  label: TieLabel;
  /** Type ids the side already holds UNENDED — shifting into one of those is refused. */
  heldTypeIds?: number[];
  /** Fired on a successful change, and on Keep as is. */
  onDone: () => void;
}

export function RelationshipShift({ label, heldTypeIds = [], onDone }: RelationshipShiftProps) {
  const { data: types = [] } = useRelationshipTypes();
  const shift = useShiftLabel();
  const [newTypeId, setNewTypeId] = useState<number | null>(null);
  const [note, setNote] = useState('');
  const [error, setError] = useState<string | null>(null);

  const becomes = `${label.type_name} becomes`;
  // Grouped the way the picker groups, and narrowed the same way: a type the side already
  // holds open is not on offer, because shifting Lover into a Lover you already hold is a
  // server refusal the player should never have been able to ask for.
  const held = new Set([...heldTypeIds, label.type]);
  const groups = FAMILIES.map(({ key, heading }) => ({
    heading,
    options: types.filter((type) => type.family === key && !held.has(type.id)),
  })).filter((group) => group.options.length > 0);

  function submit() {
    if (newTypeId == null) return;
    setError(null);
    shift.mutate(
      { label_id: label.id, new_type_id: newTypeId, note },
      {
        onSuccess: onDone,
        onError: (err: Error) => setError(err.message),
      }
    );
  }

  return (
    <div className="refsheet-block">
      <Eyebrow>Relationship Shift</Eyebrow>
      <Ledger>
        <span>{becomes}</span>
      </Ledger>
      <select
        aria-label={becomes}
        className="refsheet-input"
        value={newTypeId == null ? '' : String(newTypeId)}
        onChange={(event) => setNewTypeId(event.target.value ? Number(event.target.value) : null)}
      >
        <option value="" />
        {groups.map((group) => (
          <optgroup key={group.heading} label={group.heading}>
            {group.options.map((type) => (
              <option key={type.id} value={String(type.id)}>
                {type.name}
              </option>
            ))}
          </optgroup>
        ))}
      </select>
      <div className="refsheet-field">
        <label htmlFor={`shift-note-${label.id}`}>Note, optional</label>
        <input
          id={`shift-note-${label.id}`}
          className="refsheet-input"
          value={note}
          onChange={(event) => setNote(event.target.value)}
        />
      </div>
      {error && (
        <p role="alert" className="refsheet-note refsheet-error">
          {error}
        </p>
      )}
      <div className="refsheet-doors">
        <QuietDoor onClick={submit} disabled={newTypeId == null || shift.isPending}>
          Change
        </QuietDoor>
        <QuietDoor onClick={onDone}>Keep as is</QuietDoor>
      </div>
    </div>
  );
}

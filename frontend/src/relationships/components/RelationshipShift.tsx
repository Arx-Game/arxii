/**
 * Relationship Shift (#3957) — one label becoming another.
 *
 * Not an edit: the old row ends and a new one begins remembering it, so a tie that went
 * from Enemy to Lover still says so a year later. That is why there is no Delete
 * anywhere near this block, and why the note the player may leave rides the NEW row.
 */

import { useState } from 'react';

import { Eyebrow, QuietDoor } from '@/character_sheets/components/sheet/primitives';
import { useRelationshipTypes, useShiftLabel } from '@/relationships/queries';
import type { TieLabel } from '../api';

export interface RelationshipShiftProps {
  label: TieLabel;
  /** Fired on a successful change, and on Keep as is. */
  onDone: () => void;
}

export function RelationshipShift({ label, onDone }: RelationshipShiftProps) {
  const { data: types = [] } = useRelationshipTypes();
  const shift = useShiftLabel();
  const [newTypeId, setNewTypeId] = useState<number | null>(null);
  const [note, setNote] = useState('');
  const [error, setError] = useState<string | null>(null);

  const becomes = `${label.type_name} becomes`;
  const choices = types.filter((type) => type.id !== label.type);

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
      <p className="refsheet-ledger">
        <span>{becomes}</span>
      </p>
      <select
        aria-label={becomes}
        className="refsheet-input"
        value={newTypeId == null ? '' : String(newTypeId)}
        onChange={(event) => setNewTypeId(event.target.value ? Number(event.target.value) : null)}
      >
        <option value="" />
        {choices.map((type) => (
          <option key={type.id} value={String(type.id)}>
            {type.name}
          </option>
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

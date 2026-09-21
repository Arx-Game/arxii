/**
 * The label catalogue, as the player meets it (#3957).
 *
 * Grouped by family, because eighteen names in one column is a list and five groups of
 * four is a choice. The line under each name is the type's own authored `description`
 * — the only explanatory text anywhere in this feature, and it belongs to the content,
 * not to the interface.
 *
 * A type the tie already holds open is not offered again; one that has ended is,
 * because re-declaring a label you once held is a story, not a mistake.
 *
 * Declaring lands at Private unless the player says otherwise. That is the whole of the
 * consent design: naming what someone is to you is free and one-sided, and the default
 * is that nobody else learns it.
 */

import { useState } from 'react';

import { PillButton } from '@/journals/components/Pill';
import { Eyebrow, QuietDoor } from '@/character_sheets/components/sheet/primitives';
import { useDeclareLabel, useRelationshipTypes } from '@/relationships/queries';
import type { Awareness, RelationshipType, TieTargetRef } from '../api';

/**
 * The five families, in the order they are drawn, with their headings. Exported because
 * the shift block groups its select the same way — one order, one spelling.
 */
export const FAMILIES: Array<{ key: RelationshipType['family']; heading: string }> = [
  { key: 'heart', heading: 'Heart' },
  { key: 'company', heading: 'Company' },
  { key: 'contest', heading: 'Contest' },
  { key: 'blood_and_oath', heading: 'Blood and oath' },
  { key: 'teaching', heading: 'Teaching' },
];

const AWARENESS_PILLS: Array<{ value: Awareness; label: string }> = [
  { value: 'private', label: 'Private' },
  { value: 'clandestine', label: 'Clandestine' },
  { value: 'public', label: 'Public' },
];

export interface TypePickerProps {
  /** Which side to write to. Empty until a target is chosen on the declare-a-tie page. */
  target: TieTargetRef;
  /** Type ids the tie already holds UNENDED — those are not on offer. */
  heldTypeIds?: number[];
  /** Fired after a successful declare, so the caller can close what it opened. */
  onDeclared?: () => void;
}

export function TypePicker({ target, heldTypeIds = [], onDeclared }: TypePickerProps) {
  const { data: types = [] } = useRelationshipTypes();
  const declare = useDeclareLabel();
  const [pending, setPending] = useState<RelationshipType | null>(null);
  const [awareness, setAwareness] = useState<Awareness>('private');
  const [error, setError] = useState<string | null>(null);

  const held = new Set(heldTypeIds);
  const offered = types.filter((type) => !held.has(type.id));
  const canWrite = target.target_persona_id != null || target.target_companion_id != null;

  function submit() {
    if (!pending || !canWrite) return;
    setError(null);
    declare.mutate(
      { ...target, type_id: pending.id, awareness },
      {
        onSuccess: () => {
          setPending(null);
          setAwareness('private');
          onDeclared?.();
        },
        onError: (err: Error) => setError(err.message),
      }
    );
  }

  return (
    <div className="refsheet-picker-block">
      {error && (
        <p role="alert" className="refsheet-note refsheet-error">
          {error}
        </p>
      )}
      <div className="refsheet-picker">
        {FAMILIES.map(({ key, heading }) => {
          const group = offered.filter((type) => type.family === key);
          if (group.length === 0) return null;
          return (
            <div key={key} className="refsheet-picker-family">
              <Eyebrow>{heading}</Eyebrow>
              {group.map((type) => (
                <button
                  key={type.id}
                  type="button"
                  className="refsheet-picker-type"
                  aria-pressed={pending?.id === type.id}
                  onClick={() => setPending(type)}
                >
                  <span className="refsheet-entry-name">{type.name}</span>
                  {type.counterpart != null && (
                    <span className="refsheet-note">with {type.counterpart_name}</span>
                  )}
                  <span className="refsheet-entry-gloss">{type.description}</span>
                </button>
              ))}
            </div>
          );
        })}
      </div>
      {pending && (
        <div className="refsheet-doors">
          {AWARENESS_PILLS.map((pill) => (
            <PillButton
              key={pill.value}
              pressed={awareness === pill.value}
              onClick={() => setAwareness(pill.value)}
            >
              {pill.label}
            </PillButton>
          ))}
          <QuietDoor onClick={submit} disabled={declare.isPending || !canWrite}>
            Declare
          </QuietDoor>
        </div>
      )}
    </div>
  );
}

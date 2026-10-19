/**
 * "What works on them" (#4418, Screen 1b): the personality traits that make checks
 * against the NPC easier (a like) or harder (a dislike). Written through
 * `PUT /api/roster/npcs/{id}/preferences/`, which replaces the whole list.
 *
 * The traits to pick from are passed in (`GET /api/npc-services/personality-traits/`).
 * `copied` are the rows a "Copy from" brings; they show beside the GM's own lines and can
 * be removed, and the saved list is what is shown (see `mergePreferences`).
 */

import { useState } from 'react';
import { X } from 'lucide-react';

import { Button } from '@/components/ui/button';
import type { PreferenceLine, PreferenceValence, SavedPreference } from './npcFormApi';

export interface PersonalityTraitOption {
  id: number;
  name: string;
  description?: string;
  /** The check this trait eases when it is a like. */
  eased_check?: string | null;
}

const VALENCES: { value: PreferenceValence; label: string }[] = [
  { value: 'likes', label: 'Easier' },
  { value: 'dislikes', label: 'Harder' },
];

const selectClass = 'h-9 rounded-md border bg-transparent px-2 text-sm';

interface NpcPreferenceEditorProps {
  traits: PersonalityTraitOption[];
  lines: PreferenceLine[];
  onChange: (lines: PreferenceLine[]) => void;
  /** Rows the section's copy brings. */
  copied?: SavedPreference[];
  /** Copied rows the GM removed, by trait id. */
  removed?: number[];
  onRemovedChange?: (removed: number[]) => void;
}

interface ShownRow {
  trait: number;
  name: string;
  /** The trait's description and the check it eases, as the demo's note column. */
  note: string;
  valence: PreferenceValence;
  remove: () => void;
}

function ValencePill({ valence }: { valence: PreferenceValence }) {
  return (
    <span
      className={
        valence === 'likes'
          ? 'rounded-full border border-emerald-600/40 px-2 py-0.5 text-emerald-700 dark:text-emerald-400'
          : 'rounded-full border border-destructive/40 px-2 py-0.5 text-destructive'
      }
    >
      {valence === 'likes' ? 'Easier' : 'Harder'}
    </span>
  );
}

export function NpcPreferenceEditor({
  traits,
  lines,
  onChange,
  copied = [],
  removed = [],
  onRemovedChange = () => {},
}: NpcPreferenceEditorProps) {
  const [trait, setTrait] = useState('');
  const [valence, setValence] = useState<PreferenceValence>('likes');
  const nameOf = (id: number) =>
    traits.find((option) => option.id === id)?.name ??
    copied.find((row) => row.trait_id === id)?.trait_name ??
    String(id);

  const noteOf = (id: number, valence: PreferenceValence) => {
    const option = traits.find((candidate) => candidate.id === id);
    if (!option) return '';
    const eased = valence === 'likes' && option.eased_check ? `Eases ${option.eased_check}.` : '';
    return [option.description, eased].filter(Boolean).join(' ');
  };

  const typedTraits = new Set(lines.map((line) => line.trait));
  const rows: ShownRow[] = [
    ...copied
      .filter((row) => !removed.includes(row.trait_id) && !typedTraits.has(row.trait_id))
      .map((row) => ({
        trait: row.trait_id,
        name: row.trait_name,
        note: noteOf(row.trait_id, row.valence),
        valence: row.valence,
        remove: () => onRemovedChange([...removed, row.trait_id]),
      })),
    ...lines.map((line) => ({
      trait: line.trait,
      name: nameOf(line.trait),
      note: noteOf(line.trait, line.valence),
      valence: line.valence,
      remove: () => onChange(lines.filter((other) => other !== line)),
    })),
  ];

  const add = () => {
    if (!trait) return;
    const id = Number(trait);
    onChange([...lines.filter((line) => line.trait !== id), { trait: id, valence }]);
    setTrait('');
  };

  return (
    <div className="flex flex-col gap-2">
      {rows.length > 0 && (
        <ul className="flex flex-col gap-1 text-sm">
          {rows.map((row) => (
            <li key={row.trait} className="flex flex-wrap items-center gap-2">
              <ValencePill valence={row.valence} />
              <span className="shrink-0 font-medium">{row.name}</span>
              <span className="flex-1 text-xs text-muted-foreground" data-testid="trait-note">
                {row.note}
              </span>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                aria-label={`Remove ${row.name}`}
                onClick={row.remove}
              >
                <X className="h-3 w-3" aria-hidden="true" />
              </Button>
            </li>
          ))}
        </ul>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <select
          aria-label="Easier or harder"
          className={selectClass}
          value={valence}
          onChange={(event) => setValence(event.target.value as PreferenceValence)}
        >
          {VALENCES.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        <select
          aria-label="Trait"
          className={selectClass}
          value={trait}
          onChange={(event) => setTrait(event.target.value)}
        >
          <option value="">{traits.length === 0 ? 'No traits authored yet' : 'Trait'}</option>
          {traits.map((option) => (
            <option key={option.id} value={option.id}>
              {option.name}
            </option>
          ))}
        </select>
        <Button
          type="button"
          size="sm"
          variant="outline"
          aria-label="Add trait"
          disabled={!trait}
          onClick={add}
        >
          Add
        </Button>
      </div>
    </div>
  );
}

/**
 * "What works on them" (#4418, Screen 1b): the personality traits that make checks
 * against the NPC easier (a like) or harder (a dislike). Written through
 * `PUT /api/roster/npcs/{id}/preferences/`, which replaces the whole list.
 *
 * The traits to pick from are passed in (`GET /api/npc-services/personality-traits/`).
 */

import { useState } from 'react';
import { X } from 'lucide-react';

import { Button } from '@/components/ui/button';
import type { PreferenceLine, PreferenceValence } from './npcFormApi';

export interface PersonalityTraitOption {
  id: number;
  name: string;
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
}

export function NpcPreferenceEditor({ traits, lines, onChange }: NpcPreferenceEditorProps) {
  const [trait, setTrait] = useState('');
  const [valence, setValence] = useState<PreferenceValence>('likes');
  if (traits.length === 0) return null;
  const nameOf = (id: number) => traits.find((option) => option.id === id)?.name ?? String(id);

  const add = () => {
    if (!trait) return;
    const id = Number(trait);
    onChange([...lines.filter((line) => line.trait !== id), { trait: id, valence }]);
    setTrait('');
  };

  return (
    <div className="flex flex-col gap-2">
      {lines.length > 0 && (
        <ul className="flex flex-col gap-1 text-sm">
          {lines.map((line) => (
            <li key={line.trait} className="flex items-center gap-2">
              <span
                className={
                  line.valence === 'likes'
                    ? 'rounded-full border border-emerald-600/40 px-2 py-0.5 text-emerald-700 dark:text-emerald-400'
                    : 'rounded-full border border-destructive/40 px-2 py-0.5 text-destructive'
                }
              >
                {line.valence === 'likes' ? 'Easier' : 'Harder'}
              </span>
              <span className="flex-1">{nameOf(line.trait)}</span>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                aria-label={`Remove ${nameOf(line.trait)}`}
                onClick={() => onChange(lines.filter((other) => other !== line))}
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
          <option value="">Trait</option>
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

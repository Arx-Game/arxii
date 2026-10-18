/**
 * "Who they favor and oppose" (#4418, Screen 1b): the NPC's signed regard of a persona,
 * an organization or a society, each with a strength and a reason. Lines are gathered
 * here and written through `PUT /api/roster/npcs/{id}/regard/` when the NPC is created.
 */

import { useRef, useState } from 'react';
import { X } from 'lucide-react';

import { EntitySearchField, type EntitySearchResult } from '@/components/EntitySearchField';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { searchOrganizations, searchPersonas, searchSocieties } from '@/events/queries';
import type { RegardLine, RegardTargetType } from './npcFormApi';

/** Strength of a regard, as the signed value's size (the model's range is -1000 to 1000). */
const STRENGTHS = [
  { label: 'Mild', size: 300 },
  { label: 'Strong', size: 700 },
] as const;

const TARGET_TYPES: { value: RegardTargetType; label: string }[] = [
  { value: 'persona', label: 'Persona' },
  { value: 'organization', label: 'Organization' },
  { value: 'society', label: 'Society' },
];

const SEARCHES: Record<RegardTargetType, (query: string) => Promise<EntitySearchResult[]>> = {
  persona: searchPersonas,
  organization: searchOrganizations,
  society: searchSocieties,
};

const selectClass = 'h-9 rounded-md border bg-transparent px-2 text-sm';

function strengthLabel(value: number): string {
  return Math.abs(value) >= STRENGTHS[1].size ? STRENGTHS[1].label : STRENGTHS[0].label;
}

interface NpcRegardEditorProps {
  lines: RegardLine[];
  onChange: (lines: RegardLine[]) => void;
}

export function NpcRegardEditor({ lines, onChange }: NpcRegardEditorProps) {
  const [favors, setFavors] = useState(true);
  const [targetType, setTargetType] = useState<RegardTargetType>('organization');
  const [targetId, setTargetId] = useState<number | null>(null);
  const [size, setSize] = useState<number>(STRENGTHS[0].size);
  const [reason, setReason] = useState('');
  // The search field answers ids only; the names it showed are kept to draw the line.
  const names = useRef(new Map<string, string>());
  const search = async (query: string) => {
    const results = await SEARCHES[targetType](query);
    for (const result of results) names.current.set(`${targetType}:${result.id}`, result.name);
    return results;
  };

  const add = () => {
    if (targetId === null) return;
    const kept = lines.filter(
      (line) => !(line.target_type === targetType && line.target_id === targetId)
    );
    onChange([
      ...kept,
      {
        target_type: targetType,
        target_id: targetId,
        target_name: names.current.get(`${targetType}:${targetId}`) ?? String(targetId),
        value: favors ? size : -size,
        reason: reason.trim(),
      },
    ]);
    setTargetId(null);
    setReason('');
  };

  return (
    <div className="flex flex-col gap-2">
      {lines.length > 0 && (
        <ul className="flex flex-col gap-1 text-sm">
          {lines.map((line) => (
            <li
              key={`${line.target_type}:${line.target_id}`}
              className="flex flex-wrap items-center gap-2"
            >
              <span
                className={
                  line.value >= 0
                    ? 'rounded-full border border-emerald-600/40 px-2 py-0.5 text-emerald-700 dark:text-emerald-400'
                    : 'rounded-full border border-destructive/40 px-2 py-0.5 text-destructive'
                }
              >
                {line.value >= 0 ? '+' : '−'} {line.target_name}
              </span>
              <span className="text-muted-foreground">{strengthLabel(line.value)}</span>
              {line.reason && <span className="min-w-0 flex-1">{line.reason}</span>}
              <Button
                type="button"
                size="sm"
                variant="ghost"
                aria-label={`Remove ${line.target_name}`}
                onClick={() => onChange(lines.filter((other) => other !== line))}
              >
                <X className="h-3 w-3" aria-hidden="true" />
              </Button>
            </li>
          ))}
        </ul>
      )}
      <div className="flex flex-wrap items-end gap-2">
        <select
          aria-label="Favors or opposes"
          className={selectClass}
          value={favors ? 'favors' : 'opposes'}
          onChange={(event) => setFavors(event.target.value === 'favors')}
        >
          <option value="favors">Favors</option>
          <option value="opposes">Opposes</option>
        </select>
        <select
          aria-label="Kind of target"
          className={selectClass}
          value={targetType}
          onChange={(event) => {
            setTargetType(event.target.value as RegardTargetType);
            setTargetId(null);
          }}
        >
          {TARGET_TYPES.map((type) => (
            <option key={type.value} value={type.value}>
              {type.label}
            </option>
          ))}
        </select>
        <div className="min-w-[12rem] flex-1">
          <EntitySearchField
            key={targetType}
            label="Who"
            value={targetId}
            onChange={setTargetId}
            search={search}
          />
        </div>
        <select
          aria-label="Strength"
          className={selectClass}
          value={size}
          onChange={(event) => setSize(Number(event.target.value))}
        >
          {STRENGTHS.map((strength) => (
            <option key={strength.label} value={strength.size}>
              {strength.label}
            </option>
          ))}
        </select>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Input
          aria-label="Reason"
          placeholder="Reason"
          className="min-w-[12rem] flex-1"
          value={reason}
          onChange={(event) => setReason(event.target.value)}
          onKeyDown={(event) => {
            if (event.key !== 'Enter') return;
            event.preventDefault();
            add();
          }}
        />
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={targetId === null}
          onClick={add}
        >
          Add
        </Button>
      </div>
    </div>
  );
}

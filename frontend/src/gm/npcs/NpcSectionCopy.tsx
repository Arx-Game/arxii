/**
 * A section's "Copy from ▾" (#4418, Screen 1b): pick an NPC or template to copy this
 * section from. The copy is made when the NPC is created, before the GM's own values
 * for the section are written over it.
 */

import type { NpcCopySource } from './npcFormApi';

interface NpcSectionCopyProps {
  /** The section's heading, for the picker's label. */
  section: string;
  sources: NpcCopySource[];
  value: number | null;
  onChange: (source: number | null) => void;
  /** The blank row's text. */
  blank?: string;
}

export function NpcSectionCopy({
  section,
  sources,
  value,
  onChange,
  blank = 'Copy from',
}: NpcSectionCopyProps) {
  return (
    <select
      aria-label={`Copy ${section} from`}
      className="h-8 max-w-[16rem] rounded-md border bg-transparent px-2 text-xs text-muted-foreground"
      value={value === null ? '' : String(value)}
      onChange={(event) => onChange(event.target.value === '' ? null : Number(event.target.value))}
    >
      <option value="">{blank}</option>
      {sources.map((source) => (
        <option key={source.id} value={source.id}>
          {source.label}
        </option>
      ))}
    </select>
  );
}

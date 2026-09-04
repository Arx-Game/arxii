/**
 * OpponentLinesEditor - repeatable bestiary-row editor for an
 * encounter's opponent lines.
 *
 * Shared by BeatFormDialog (a Beat's session-prep opponent lines,
 * #3425) and OptionPage (a MissionOption's authored opponent lines on
 * an ENCOUNTER option, #3565) - both authoring surfaces spawn the same
 * shape of encounter, so they share this editor rather than each
 * growing its own bestiary-row UI.
 *
 * Operates on the caller's own draft state (string-typed rows, so a
 * half-typed count doesn't fight the input) - the caller owns
 * converting to/from its own payload shape (creature_template as a
 * number, etc.) since that shape differs between Beat and MissionOption.
 */

import { useState } from 'react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useCreatureTemplates } from '@/combat/queries';

/** Draft shape for one opponent-line row while the form is open. */
export interface OpponentLineDraft {
  id?: number;
  creature_template: string;
  count: string;
  position_name: string;
}

export interface OpponentLinesEditorProps {
  lines: OpponentLineDraft[];
  onChange: (lines: OpponentLineDraft[]) => void;
  rowErrors: Record<string, string[]>[] | undefined;
}

export function OpponentLinesEditor({ lines, onChange, rowErrors }: OpponentLinesEditorProps) {
  const [search, setSearch] = useState('');
  const { data: creatureTemplates = [] } = useCreatureTemplates(search);

  function updateRow(index: number, partial: Partial<OpponentLineDraft>) {
    onChange(lines.map((line, i) => (i === index ? { ...line, ...partial } : line)));
  }

  function addRow() {
    onChange([...lines, { creature_template: '', count: '1', position_name: '' }]);
  }

  function removeRow(index: number) {
    onChange(lines.filter((_, i) => i !== index));
  }

  return (
    <div className="space-y-2" data-testid="beat-opponent-lines">
      <div className="flex items-center justify-between">
        <Label>Encounter prep - opponent lines</Label>
        <Button type="button" size="sm" variant="outline" onClick={addRow}>
          Add opponent
        </Button>
      </div>
      <Input
        placeholder="Search the bestiary…"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
      />
      {lines.length === 0 && (
        <p className="text-xs text-muted-foreground">No opponents authored yet.</p>
      )}
      {lines.map((line, index) => {
        const errors = rowErrors?.[index];
        return (
          <div
            key={line.id ?? `new-${index}`}
            className="grid grid-cols-[1fr_auto_1fr_auto] items-start gap-2 rounded-md border p-2"
            data-testid={`beat-opponent-line-row-${index}`}
          >
            <div className="space-y-1">
              <select
                className="w-full rounded-md border bg-background px-2 py-1.5 text-sm"
                value={line.creature_template}
                onChange={(e) => updateRow(index, { creature_template: e.target.value })}
                data-testid={`beat-opponent-line-creature-${index}`}
              >
                <option value="">Select a creature…</option>
                {creatureTemplates.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name} ({t.tier})
                  </option>
                ))}
              </select>
              {errors?.creature_template && (
                <p className="text-xs text-destructive">{errors.creature_template.join(' ')}</p>
              )}
            </div>
            <Input
              type="number"
              min={1}
              className="w-16"
              value={line.count}
              onChange={(e) => updateRow(index, { count: e.target.value })}
              data-testid={`beat-opponent-line-count-${index}`}
            />
            <Input
              placeholder="Position (optional)"
              value={line.position_name}
              onChange={(e) => updateRow(index, { position_name: e.target.value })}
              data-testid={`beat-opponent-line-position-${index}`}
            />
            <Button
              type="button"
              size="sm"
              variant="ghost"
              onClick={() => removeRow(index)}
              data-testid={`beat-opponent-line-remove-${index}`}
            >
              Remove
            </Button>
          </div>
        );
      })}
    </div>
  );
}

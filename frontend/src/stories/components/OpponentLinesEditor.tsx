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
 *
 * With `showPlacement` (#4361) each line with a creature picked gets a
 * PlacementPanel: the line's standoff edits over its template. The placement
 * fields share one draft and payload shape on both surfaces
 * (`placementFieldsFromLine` / `placementPayload`).
 */

import { useState } from 'react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useCreatureTemplates, usePlacementPersonas } from '@/combat/queries';
import type { PersonaScope } from '@/combat/api';

import { PlacementPanel } from './PlacementPanel';
import type { PlacementDraft } from './placementDraft';

/** Draft shape for one opponent-line row while the form is open. */
export interface OpponentLineDraft extends PlacementDraft {
  id?: number;
  creature_template: string;
  count: string;
  position_name: string;
  /** Beat lines only (#4354): the line opens the encounter as a standoff. */
  opens_as_standoff?: boolean;
  /** Beat lines only (#4373): a named NPC who stands as the line's one opponent. */
  persona?: number | null;
  persona_name?: string;
}

export interface OpponentLinesEditorProps {
  lines: OpponentLineDraft[];
  onChange: (lines: OpponentLineDraft[]) => void;
  rowErrors: Record<string, string[]>[] | undefined;
  /** Show the per-line "Opens as a standoff" checkbox (beats only, not mission options). */
  showStandoffSwitch?: boolean;
  /** Show each line's standoff placement panel (#4361). */
  showPlacement?: boolean;
  /**
   * Offer a named NPC per line (#4373): the personas this scope's story already uses.
   * Beat lines only; mission option lines have no named NPCs.
   */
  personaScope?: PersonaScope;
}

function NamedNpcPicker({
  index,
  scope,
  line,
  onPick,
}: {
  index: number;
  scope: PersonaScope;
  line: OpponentLineDraft;
  onPick: (persona: number | null, name: string) => void;
}) {
  const { data: personas = [] } = usePlacementPersonas(scope);
  const current = line.persona ?? null;
  return (
    <label className="col-span-full flex flex-wrap items-center gap-2 text-sm">
      <span className="text-xs text-muted-foreground">Named NPC</span>
      <select
        className="rounded-md border bg-background px-2 py-1.5 text-sm"
        value={current ? String(current) : ''}
        onChange={(e) => {
          const id = e.target.value ? Number(e.target.value) : null;
          const pick = personas.find((p) => p.id === id);
          onPick(id, pick?.name ?? '');
        }}
        aria-label="Named NPC"
        data-testid={`beat-opponent-line-persona-${index}`}
      >
        <option value="">None: the creatures themselves</option>
        {current && !personas.some((p) => p.id === current) && (
          <option value={String(current)}>{line.persona_name}</option>
        )}
        {personas.map((p) => (
          <option key={p.id} value={String(p.id)}>
            {p.name}
          </option>
        ))}
      </select>
      {personas.length === 0 && !current && (
        <span className="text-xs text-muted-foreground">
          Name an NPC in this story&apos;s stakes or protected subjects to stand them here.
        </span>
      )}
    </label>
  );
}

export function OpponentLinesEditor({
  lines,
  onChange,
  rowErrors,
  showStandoffSwitch = false,
  showPlacement = false,
  personaScope,
}: OpponentLinesEditorProps) {
  const [search, setSearch] = useState('');
  const { data: creatureTemplates = [] } = useCreatureTemplates(search);

  function updateRow(index: number, partial: Partial<OpponentLineDraft>) {
    onChange(lines.map((line, i) => (i === index ? { ...line, ...partial } : line)));
  }

  function addRow() {
    onChange([
      ...lines,
      { creature_template: '', count: '1', position_name: '', opens_as_standoff: false },
    ]);
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
                onChange={(e) =>
                  // A new creature has other drives and rules: its edits start over.
                  updateRow(index, {
                    creature_template: e.target.value,
                    drive_edits: [],
                    suppressed_faction_rules: [],
                  })
                }
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
              disabled={Boolean(line.persona)}
              title={line.persona ? 'A named NPC stands alone.' : undefined}
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
            {personaScope && (
              <NamedNpcPicker
                index={index}
                scope={personaScope}
                line={line}
                onPick={(persona, name) =>
                  // A named NPC stands alone, and their drives are their persona's own.
                  updateRow(index, {
                    persona,
                    persona_name: name,
                    ...(persona ? { count: '1', drive_edits: [] } : {}),
                  })
                }
              />
            )}
            {showPlacement && line.creature_template !== '' && (
              <PlacementPanel
                index={index}
                templateId={Number(line.creature_template)}
                count={line.count}
                draft={line}
                onChange={(partial) => updateRow(index, partial)}
                showStandoffSwitch={showStandoffSwitch}
                personaName={line.persona ? line.persona_name : ''}
              />
            )}
            {Object.entries(errors ?? {})
              .filter(([key]) =>
                [
                  'drive_edits',
                  'suppressed_faction_rules',
                  'organization',
                  'cause_override',
                  'persona',
                  'count',
                ].includes(key)
              )
              .map(([key, messages]) => (
                <p key={key} className="col-span-full text-xs text-destructive">
                  {messages.join(' ')}
                </p>
              ))}
            {showStandoffSwitch && !(showPlacement && line.creature_template !== '') && (
              <label className="col-span-full flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={line.opens_as_standoff ?? false}
                  onChange={(e) => updateRow(index, { opens_as_standoff: e.target.checked })}
                  data-testid={`beat-opponent-line-standoff-${index}`}
                />
                Opens as a standoff
              </label>
            )}
          </div>
        );
      })}
    </div>
  );
}

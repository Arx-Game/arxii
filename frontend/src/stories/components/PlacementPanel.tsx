/**
 * PlacementPanel (#4361): one opponent line's standoff edits over its creature
 * template, in the story author's beat dialog and the mission studio's option page.
 *
 * The same fields as the staff Placement page, shown beside the template's own
 * values: "opens as a standoff" (beats only), the cause, the affiliation, the
 * drives (raise, lower, remove, add from the property catalog) and a switch-off box
 * per inherited faction rule with where it came from. Every pick comes from a
 * catalog (ADR-0110); the server validates the same way the admin page does.
 */

import { useState } from 'react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { usePlacementContext, usePlacementPicks } from '@/combat/queries';
import type { PlacementContext } from '@/combat/api';

import {
  CAUSES,
  REMOVE,
  SAME,
  STRENGTHS,
  pickValue,
  placementSummary,
  type PlacementDraft,
} from './placementDraft';

interface PlacementPanelProps {
  index: number;
  templateId: number;
  count: string;
  draft: PlacementDraft;
  onChange: (partial: PlacementDraft) => void;
  showStandoffSwitch: boolean;
  /** Set when the line stands a named NPC (#4373): drives come from the persona. */
  personaName?: string;
}

function AffiliationPicker({
  index,
  context,
  draft,
  onChange,
}: {
  index: number;
  context: PlacementContext;
  draft: PlacementDraft;
  onChange: (partial: PlacementDraft) => void;
}) {
  const [search, setSearch] = useState('');
  const { data: picks = [] } = usePlacementPicks('organizations', search, search.length > 0);
  const templateLabel = context.organization_name
    ? `${context.organization_name} (template)`
    : 'No affiliation (template)';
  return (
    <div className="flex min-w-0 flex-col gap-1">
      <span className="text-xs text-muted-foreground">Affiliation</span>
      <select
        className="rounded-md border bg-background px-2 py-1.5 text-sm"
        value={draft.organization ? String(draft.organization) : ''}
        onChange={(e) => {
          const id = e.target.value ? Number(e.target.value) : null;
          const pick = picks.find((p) => p.id === id);
          onChange({
            organization: id,
            organization_name: pick?.name ?? '',
            suppressed_faction_rules: [],
          });
        }}
        aria-label="Affiliation"
        data-testid={`placement-affiliation-${index}`}
      >
        <option value="">{templateLabel}</option>
        {draft.organization && !picks.some((p) => p.id === draft.organization) && (
          <option value={String(draft.organization)}>{draft.organization_name}</option>
        )}
        {picks.map((p) => (
          <option key={p.id} value={String(p.id)}>
            {p.name}
          </option>
        ))}
      </select>
      <Input
        placeholder="Search organizations…"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        className="h-7 text-xs"
      />
    </div>
  );
}

function DriveTable({
  index,
  context,
  draft,
  onChange,
}: {
  index: number;
  context: PlacementContext;
  draft: PlacementDraft;
  onChange: (partial: PlacementDraft) => void;
}) {
  const [adding, setAdding] = useState(false);
  const [search, setSearch] = useState('');
  const { data: picks = [] } = usePlacementPicks('properties', search, adding);
  const edits = draft.drive_edits ?? [];
  const byProperty = new Map(edits.map((e) => [e.property, e]));
  const added = edits.filter((e) => !context.drives.some((d) => d.property === e.property));

  function setEdit(property: number, name: string, value: string) {
    const rest = edits.filter((e) => e.property !== property);
    if (value === SAME) {
      onChange({ drive_edits: rest });
      return;
    }
    const strength = value === REMOVE ? null : Number(value);
    onChange({ drive_edits: [...rest, { property, property_name: name, strength }] });
  }

  function addDrive(property: number, name: string) {
    if (byProperty.has(property) || context.drives.some((d) => d.property === property)) return;
    onChange({ drive_edits: [...edits, { property, property_name: name, strength: 1 }] });
    setAdding(false);
    setSearch('');
  }

  return (
    <div className="flex flex-col gap-1">
      <table className="w-full border-collapse text-xs" data-testid={`placement-drives-${index}`}>
        <thead>
          <tr className="text-left text-[10px] uppercase tracking-wide text-muted-foreground">
            <th className="py-1 pr-2 font-medium">Drive</th>
            <th className="py-1 pr-2 font-medium">Template</th>
            <th className="py-1 font-medium">Here</th>
          </tr>
        </thead>
        <tbody>
          {context.drives.map((drive) => {
            const edit = byProperty.get(drive.property);
            const value = pickValue(edit);
            return (
              <tr key={drive.property} className="border-t border-border align-middle">
                <td className="py-1 pr-2">{drive.name}</td>
                <td className="py-1 pr-2">{drive.strength_label}</td>
                <td className="flex flex-wrap items-center gap-2 py-1">
                  <select
                    className="rounded-md border bg-background px-1 py-0.5 text-xs"
                    value={value}
                    onChange={(e) => setEdit(drive.property, drive.name, e.target.value)}
                    aria-label={`${drive.name} here`}
                  >
                    <option value={SAME}>Same</option>
                    {STRENGTHS.map((s) => (
                      <option key={s.value} value={String(s.value)}>
                        {s.label}
                      </option>
                    ))}
                    <option value={REMOVE}>Remove</option>
                  </select>
                  {edit && (
                    <span className="font-mono text-[10px] text-violet-700 dark:text-violet-300">
                      {edit.strength === null ? 'removed' : 'edited'}
                    </span>
                  )}
                </td>
              </tr>
            );
          })}
          {added.map((edit) => (
            <tr key={edit.property} className="border-t border-border align-middle">
              <td className="py-1 pr-2">{edit.property_name}</td>
              <td className="py-1 pr-2 text-muted-foreground">none</td>
              <td className="flex flex-wrap items-center gap-2 py-1">
                <select
                  className="rounded-md border bg-background px-1 py-0.5 text-xs"
                  value={String(edit.strength ?? 1)}
                  onChange={(e) => setEdit(edit.property, edit.property_name, e.target.value)}
                  aria-label={`${edit.property_name} here`}
                >
                  {STRENGTHS.map((s) => (
                    <option key={s.value} value={String(s.value)}>
                      {s.label}
                    </option>
                  ))}
                </select>
                <span className="font-mono text-[10px] text-violet-700 dark:text-violet-300">
                  added
                </span>
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  className="h-6 px-2 text-xs"
                  onClick={() => setEdit(edit.property, edit.property_name, SAME)}
                >
                  Remove
                </Button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {adding ? (
        <div className="flex flex-wrap items-center gap-2">
          <Input
            placeholder="Search properties…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="h-7 w-48 text-xs"
            aria-label="Search properties"
          />
          <select
            className="rounded-md border bg-background px-1 py-0.5 text-xs"
            value=""
            onChange={(e) => {
              const pick = picks.find((p) => p.id === Number(e.target.value));
              if (pick) addDrive(pick.id, pick.name);
            }}
            aria-label="Drive to add"
            data-testid={`placement-add-drive-${index}`}
          >
            <option value="">Pick a drive…</option>
            {picks.map((p) => (
              <option key={p.id} value={String(p.id)}>
                {p.name}
              </option>
            ))}
          </select>
          <Button type="button" size="sm" variant="ghost" onClick={() => setAdding(false)}>
            Cancel
          </Button>
        </div>
      ) : (
        <Button
          type="button"
          size="sm"
          variant="ghost"
          className="self-start text-xs"
          onClick={() => setAdding(true)}
        >
          + Add a drive
        </Button>
      )}
    </div>
  );
}

function RulesTable({
  index,
  context,
  draft,
  onChange,
}: {
  index: number;
  context: PlacementContext;
  draft: PlacementDraft;
  onChange: (partial: PlacementDraft) => void;
}) {
  const off = new Set(draft.suppressed_faction_rules ?? []);
  if (context.inherited_rules.length === 0) {
    return <p className="text-xs text-muted-foreground">This line inherits no faction rules.</p>;
  }
  function toggle(id: number, checked: boolean) {
    const next = new Set(off);
    if (checked) next.add(id);
    else next.delete(id);
    onChange({ suppressed_faction_rules: [...next].sort((a, b) => a - b) });
  }
  return (
    <table className="w-full border-collapse text-xs" data-testid={`placement-rules-${index}`}>
      <thead>
        <tr className="text-left text-[10px] uppercase tracking-wide text-muted-foreground">
          <th className="py-1 pr-2 font-medium">Inherited faction rule</th>
          <th className="py-1 pr-2 font-medium">From</th>
          <th className="py-1 font-medium">Off here</th>
        </tr>
      </thead>
      <tbody>
        {context.inherited_rules.map((rule) => (
          <tr key={rule.faction_rule_id} className="border-t border-border align-middle">
            <td className="py-1 pr-2">{rule.label}</td>
            <td className="py-1 pr-2">{rule.source}</td>
            <td className="py-1">
              <input
                type="checkbox"
                checked={off.has(rule.faction_rule_id)}
                onChange={(e) => toggle(rule.faction_rule_id, e.target.checked)}
                aria-label={`Off: ${rule.label}`}
              />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function PlacementPanel({
  index,
  templateId,
  count,
  draft,
  onChange,
  showStandoffSwitch,
  personaName = '',
}: PlacementPanelProps) {
  const { data: context } = usePlacementContext(templateId, draft.organization ?? null);
  return (
    <div
      className="col-span-full flex flex-col gap-2 rounded-md border border-dashed border-violet-500/60 bg-violet-500/5 p-2"
      data-testid={`placement-panel-${index}`}
    >
      <span className="text-sm font-semibold">Standoff for this line</span>
      {showStandoffSwitch && (
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={draft.opens_as_standoff ?? false}
            onChange={(e) => onChange({ opens_as_standoff: e.target.checked })}
            data-testid={`beat-opponent-line-standoff-${index}`}
          />
          Opens as a standoff
        </label>
      )}
      {context ? (
        <>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            <div className="flex min-w-0 flex-col gap-1">
              <span className="text-xs text-muted-foreground">Cause</span>
              <select
                className="rounded-md border bg-background px-2 py-1.5 text-sm"
                value={draft.cause_override ?? ''}
                onChange={(e) => onChange({ cause_override: e.target.value })}
                aria-label="Cause"
                data-testid={`placement-cause-${index}`}
              >
                <option value="">{`${context.cause_label} (template)`}</option>
                {CAUSES.map((c) => (
                  <option key={c.value} value={c.value}>
                    {c.label}
                  </option>
                ))}
              </select>
            </div>
            <AffiliationPicker index={index} context={context} draft={draft} onChange={onChange} />
          </div>
          {personaName ? (
            <p className="text-xs text-muted-foreground" data-testid={`placement-persona-${index}`}>
              {personaName} is a named NPC: their drives are their persona&apos;s properties, edited
              on the persona, not here.
            </p>
          ) : (
            <DriveTable index={index} context={context} draft={draft} onChange={onChange} />
          )}
          <RulesTable index={index} context={context} draft={draft} onChange={onChange} />
          <span
            className="text-xs text-muted-foreground"
            data-testid={`placement-summary-${index}`}
          >
            {placementSummary(context, draft, count, personaName)}
          </span>
        </>
      ) : (
        <span className="text-xs text-muted-foreground">Loading the template's profile…</span>
      )}
    </div>
  );
}

/**
 * Placement draft state and helpers (#4361), shared by PlacementPanel,
 * OpponentLinesEditor, the beat dialog and the mission studio's option page.
 */

import type { PlacementContext } from '@/combat/api';

/** One drive edit while the form is open: a strength, or null to remove the drive. */
export interface DriveEditDraft {
  property: number;
  property_name: string;
  strength: number | null;
}

/** The placement fields an opponent line draft carries; undefined means "as the template". */
export interface PlacementDraft {
  opens_as_standoff?: boolean;
  cause_override?: string;
  cause_margin_override?: number | null;
  organization?: number | null;
  organization_name?: string;
  drive_edits?: DriveEditDraft[];
  suppressed_faction_rules?: number[];
}

export const CAUSES: { value: string; label: string }[] = [
  { value: 'none', label: 'None' },
  { value: 'predation', label: 'Predation' },
  { value: 'orders', label: 'Orders' },
];

export const STRENGTHS: { value: number; label: string }[] = [
  { value: 1, label: 'Minor' },
  { value: 2, label: 'Major' },
  { value: 3, label: 'Defining' },
];

export const SAME = 'same';
export const REMOVE = 'remove';

function strengthLabel(value: number | null | undefined): string {
  return STRENGTHS.find((s) => s.value === value)?.label ?? '';
}

function causeLabel(value: string): string {
  return CAUSES.find((c) => c.value === value)?.label ?? value;
}

/** The plain one-line summary of what the line will spawn. */
export function placementSummary(
  context: PlacementContext,
  draft: PlacementDraft,
  count: string,
  personaName = ''
): string {
  const edits = new Map((draft.drive_edits ?? []).map((e) => [e.property, e]));
  const drives: string[] = [];
  for (const drive of context.drives) {
    const edit = edits.get(drive.property);
    const strength = edit ? edit.strength : drive.strength;
    if (strength) drives.push(`${drive.name} (${strengthLabel(strength)})`);
  }
  for (const edit of draft.drive_edits ?? []) {
    if (!context.drives.some((d) => d.property === edit.property) && edit.strength) {
      drives.push(`${edit.property_name} (${strengthLabel(edit.strength)})`);
    }
  }
  const off = new Set(draft.suppressed_faction_rules ?? []);
  const rules = context.inherited_rules.filter((r) => !off.has(r.faction_rule_id)).length;
  const cause = causeLabel(draft.cause_override || context.cause);
  const speaks = context.language_name ? `speaks ${context.language_name}` : 'no language';
  if (personaName) {
    // A named NPC's drives and languages are their persona's own (#4373).
    return `Stands ${personaName} (${context.name}): ${cause}, drives from their persona, ${rules} faction rule${rules === 1 ? '' : 's'}.`;
  }
  const parts = [
    `Spawns ${count || '1'} ${context.name}: ${cause}`,
    drives.length ? drives.join(', ') : 'no drives',
    `${rules} faction rule${rules === 1 ? '' : 's'}`,
    speaks,
  ];
  return `${parts.join(', ')}.`;
}

/** The "Here" pick for one template drive: same, a strength, or removed. */
export function pickValue(edit: DriveEditDraft | undefined): string {
  if (!edit) return SAME;
  return edit.strength === null ? REMOVE : String(edit.strength);
}

/** The placement fields as either line API returns them (#4361). */
export interface PlacementLineFields {
  cause_override?: string;
  cause_margin_override?: number | null;
  organization?: number | null;
  organization_name?: string;
  drive_edits?: { property: number; property_name?: string; strength: number | null }[];
  suppressed_faction_rules?: number[];
}

/** A saved line's placement fields as draft state. */
export function placementFieldsFromLine(line: PlacementLineFields): PlacementDraft {
  return {
    cause_override: line.cause_override ?? '',
    cause_margin_override: line.cause_margin_override ?? null,
    organization: line.organization ?? null,
    organization_name: line.organization_name ?? '',
    drive_edits: (line.drive_edits ?? []).map(
      (e): DriveEditDraft => ({
        property: e.property,
        property_name: e.property_name ?? '',
        strength: e.strength,
      })
    ),
    suppressed_faction_rules: line.suppressed_faction_rules ?? [],
  };
}

/**
 * A draft's placement fields as the line API takes them. `organization_name` is read
 * only on the server; it rides along because the beat and option payloads reuse the
 * read types.
 */
export function placementPayload(draft: PlacementDraft) {
  return {
    cause_override: (draft.cause_override ?? '') as '' | 'none' | 'predation' | 'orders',
    cause_margin_override: draft.cause_margin_override ?? null,
    organization: draft.organization ?? null,
    organization_name: draft.organization_name ?? '',
    drive_edits: (draft.drive_edits ?? []).map((e) => ({
      property: e.property,
      property_name: e.property_name,
      strength: e.strength as 1 | 2 | 3 | null,
    })),
    suppressed_faction_rules: draft.suppressed_faction_rules ?? [],
  };
}

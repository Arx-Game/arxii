/**
 * The GM's NPC form (#4418, Screens 1a and 1b): what it reads and how "Create NPC"
 * writes. Minting goes through the `mint_story_npc` registry action; every section the
 * GM filled in is then written through the seam that already owns it (the staff sheet
 * edit for identity and prose, the NPC API for regard, preferences, notes and lending),
 * and every section with a "Copy from" is copied from that NPC or template first.
 * A section left blank and not copied is never written.
 */

import { postDispatchAction } from '@/combat/api';
import { isDispatchFailure } from '@/combat/types';
import { patchStaffEdit, type StaffEditBody } from '@/character_sheets/api';
import { apiFetch } from '@/evennia_replacements/api';
import type { components } from '@/generated/api';
import { throwApiError } from '@/lib/errors';
import { fetchRosterEntry } from '@/roster/api';

export type NpcRow = components['schemas']['NPCRosterRow'];
type NpcRowPage = components['schemas']['PaginatedNPCRosterRowList'];
export type StatlinePreset = components['schemas']['NPCStatlinePreset'];
type StatlinePresetPage = components['schemas']['PaginatedNPCStatlinePresetList'];
export type NpcSettingsPatch = components['schemas']['PatchedNPCDetailRequest'];
export type LendPolicy = components['schemas']['LendPolicyEnum'];
export type BorrowAudience = components['schemas']['BorrowAudienceEnum'];

/** `world.roster.constants.NPCSection`: the parts `copy-section` copies. */
export type NpcSection =
  | 'identity'
  | 'description'
  | 'background'
  | 'powers'
  | 'regard'
  | 'preferences';

/** `world.npc_services.constants.RegardTargetType`. */
export type RegardTargetType = 'persona' | 'organization' | 'society';

/** One line of "Who they favor and oppose": a signed regard of one target. */
export interface RegardLine {
  target_type: RegardTargetType;
  target_id: number;
  /** Shown on the line; not sent. */
  target_name: string;
  /** Signed, -1000 to 1000 (`world.npc_services.models.REGARD_MIN`/`REGARD_MAX`). */
  value: number;
  reason: string;
}

/** `world.npc_services.models.PreferenceValence`: a like eases checks, a dislike hardens. */
export type PreferenceValence = 'likes' | 'dislikes';

export interface PreferenceLine {
  trait: number;
  valence: PreferenceValence;
}

/** A source for "Copy from": an NPC or template the GM may copy. */
export interface NpcCopySource {
  id: number;
  label: string;
}

// ---------------------------------------------------------------------------
// Reads
// ---------------------------------------------------------------------------

/** The templates the GM may start from: their own, and the ones staff curate. */
export async function fetchNpcTemplates(): Promise<NpcRow[]> {
  const res = await apiFetch('/api/roster/npcs/templates/');
  if (!res.ok) await throwApiError(res, 'Failed to load the NPC templates');
  const body = (await res.json()) as NpcRowPage;
  return body.results;
}

/** The curated stat blocks a new NPC can be minted with. */
export async function fetchStatlinePresets(): Promise<StatlinePreset[]> {
  const res = await apiFetch('/api/roster/npc-presets/');
  if (!res.ok) await throwApiError(res, 'Failed to load the stat blocks');
  const body = (await res.json()) as StatlinePresetPage;
  return body.results;
}

/** The sheet behind a roster entry (the sheet id is the character id). */
export async function fetchSheetIdForEntry(entryId: number): Promise<number> {
  const entry = await fetchRosterEntry(entryId);
  return entry.character.id;
}

// ---------------------------------------------------------------------------
// Writes
// ---------------------------------------------------------------------------

/** Mint through `mint_story_npc`; answers the new roster entry's id. */
export async function mintNpc(
  characterId: number,
  kwargs: { name: string; description: string; preset: string }
): Promise<number> {
  const sent: Record<string, string> = { name: kwargs.name };
  if (kwargs.description) sent.description = kwargs.description;
  if (kwargs.preset) sent.preset = kwargs.preset;
  const result = await postDispatchAction(characterId, {
    ref: { backend: 'registry', registry_key: 'mint_story_npc' },
    kwargs: sent,
  });
  if (isDispatchFailure(result)) throw new Error(result.message ?? 'The NPC was not created.');
  const entryId = result.data?.roster_entry_id;
  if (typeof entryId !== 'number') throw new Error('The NPC was not created.');
  return entryId;
}

async function sendNpc(
  url: string,
  method: 'POST' | 'PUT' | 'PATCH',
  body: unknown,
  fallback: string
): Promise<Response> {
  const res = await apiFetch(url, { method, body: JSON.stringify(body) });
  if (!res.ok) await throwApiError(res, fallback);
  return res;
}

export async function copyNpcSection(
  targetEntryId: number,
  sourceEntryId: number,
  section: NpcSection
): Promise<void> {
  await sendNpc(
    `/api/roster/npcs/${targetEntryId}/copy-section/`,
    'POST',
    { source_entry: sourceEntryId, section },
    'The section was not copied.'
  );
}

/** A copy of an NPC under a new name; answers the copy's roster entry id. */
export async function copyNpcAsNew(
  sourceEntryId: number,
  name: string,
  asTemplate: boolean
): Promise<number> {
  const res = await sendNpc(
    `/api/roster/npcs/${sourceEntryId}/copy-as-new/`,
    'POST',
    { name, as_template: asTemplate },
    'The copy was not made.'
  );
  const body = (await res.json()) as { id: number };
  return body.id;
}

export async function putNpcRegard(entryId: number, line: RegardLine): Promise<void> {
  await sendNpc(
    `/api/roster/npcs/${entryId}/regard/`,
    'PUT',
    {
      target_type: line.target_type,
      target_id: line.target_id,
      value: line.value,
      reason: line.reason,
    },
    'Who they favor and oppose was not saved.'
  );
}

export async function putNpcPreferences(entryId: number, lines: PreferenceLine[]): Promise<void> {
  await sendNpc(
    `/api/roster/npcs/${entryId}/preferences/`,
    'PUT',
    { preferences: lines },
    'What works on them was not saved.'
  );
}

export async function patchNpcSettings(entryId: number, body: NpcSettingsPatch): Promise<void> {
  await sendNpc(`/api/roster/npcs/${entryId}/`, 'PATCH', body, 'The NPC settings were not saved.');
}

// ---------------------------------------------------------------------------
// Create NPC
// ---------------------------------------------------------------------------

/** Everything the form gathered. Blank strings, nulls and empty lists mean "not filled". */
export interface NpcFormDraft {
  name: string;
  description: string;
  /** A stat block's name, or ''. */
  preset: string;
  /** "Start from": what fills every section the GM left blank. */
  startFrom: number | null;
  /** A section's own "Copy from", copied before the GM's own values are written. */
  sectionCopies: Partial<Record<NpcSection, number>>;
  /** Identity and prose, as the staff sheet edit takes them. */
  sheet: StaffEditBody;
  regard: RegardLine[];
  preferences: PreferenceLine[];
  /** Lending settings and notes the GM changed. */
  settings: NpcSettingsPatch;
}

const IDENTITY_KEYS = [
  'gender',
  'pronouns',
  'species',
  'ic_birth_year',
  'true_height_inches',
  'build',
  'vocation',
  'social_rank',
  'family',
] as const;
const BACKGROUND_KEYS = ['concept', 'protect', 'fear', 'never_do', 'background'] as const;

function sectionFilled(draft: NpcFormDraft, section: NpcSection): boolean {
  const sheet = draft.sheet as Record<string, unknown>;
  switch (section) {
    case 'identity':
      return IDENTITY_KEYS.some((key) => sheet[key] !== undefined);
    case 'description':
      return draft.description !== '';
    case 'background':
      return BACKGROUND_KEYS.some((key) => sheet[key] !== undefined);
    case 'powers':
      return draft.preset !== '';
    case 'regard':
      return draft.regard.length > 0;
    case 'preferences':
      return draft.preferences.length > 0;
  }
}

const SECTIONS: NpcSection[] = [
  'identity',
  'description',
  'background',
  'powers',
  'regard',
  'preferences',
];

/** Where each section copies from: its own "Copy from", else "Start from" when left blank. */
export function plannedCopies(draft: NpcFormDraft): [NpcSection, number][] {
  const copies: [NpcSection, number][] = [];
  for (const section of SECTIONS) {
    const own = draft.sectionCopies[section];
    if (own !== undefined) copies.push([section, own]);
    else if (draft.startFrom !== null && !sectionFilled(draft, section)) {
      copies.push([section, draft.startFrom]);
    }
  }
  return copies;
}

/**
 * Mint, copy, then write only what was filled in. Answers the new roster entry's id.
 * A failure after the mint leaves the NPC minted; the error says which part failed.
 */
export async function createNpc(characterId: number, draft: NpcFormDraft): Promise<number> {
  const entryId = await mintNpc(characterId, {
    name: draft.name.trim(),
    description: draft.description,
    preset: draft.preset,
  });
  for (const [section, source] of plannedCopies(draft)) {
    await copyNpcSection(entryId, source, section);
  }
  if (Object.keys(draft.sheet).length > 0) {
    const sheetId = await fetchSheetIdForEntry(entryId);
    await patchStaffEdit(sheetId, draft.sheet);
  }
  for (const line of draft.regard) {
    await putNpcRegard(entryId, line);
  }
  if (draft.preferences.length > 0) {
    await putNpcPreferences(entryId, draft.preferences);
  }
  if (Object.keys(draft.settings).length > 0) {
    await patchNpcSettings(entryId, draft.settings);
  }
  return entryId;
}

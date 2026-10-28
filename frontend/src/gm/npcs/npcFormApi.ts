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
import {
  fetchCharacterSheet,
  patchStaffEdit,
  runStaffRowAction,
  type StaffEditBody,
} from '@/character_sheets/api';
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

export const LEND_POLICIES: { value: LendPolicy; label: string }[] = [
  { value: 'not_lent', label: 'Only me' },
  { value: 'on_request', label: 'Me, and anyone I lend them to' },
  { value: 'without_asking', label: 'Anyone who borrows them, without asking' },
];
export const BORROW_AUDIENCES: { value: BorrowAudience; label: string }[] = [
  { value: 'gms', label: 'Any GM' },
  { value: 'gms_and_guides', label: 'Any GM or Guide' },
];

type Schemas = components['schemas'];
type CopySectionRequest = Schemas['CopySectionRequest'];
type CopyAsNewRequest = Schemas['CopyAsNewRequest'];
type RegardRequest = Schemas['RegardRequest'];
type PreferencesRequest = Schemas['PreferencesRequest'];
export type PersonalityTrait = Schemas['PersonalityTrait'];
type PersonalityTraitPage = Schemas['PaginatedPersonalityTraitList'];

/** The parts `copy-section` copies one at a time (every `SectionEnum` but `all`). */
export type NpcSection = Exclude<CopySectionRequest['section'], 'all'>;

export type RegardTargetType = RegardRequest['target_type'];

/** One line of "Who they favor and oppose": the regard as sent, plus the name shown. */
export type RegardLine = RegardRequest & { target_name: string };

/** A like eases checks against the NPC, a dislike hardens them. */
export type PreferenceLine = PreferencesRequest['preferences'][number];
export type PreferenceValence = PreferenceLine['valence'];

/** The owner's view of one NPC, with its saved preferences and regard. */
export type NpcDetail = Schemas['NPCDetail'];
export type SavedPreference = NpcDetail['preferences'][number];
export type SavedRegard = NpcDetail['regard'][number];

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

/** Every active personality trait, for "What works on them" (every page). */
export async function fetchPersonalityTraits(): Promise<PersonalityTrait[]> {
  const traits: PersonalityTrait[] = [];
  for (let page = 1; ; page += 1) {
    const res = await apiFetch(`/api/npc-services/personality-traits/?page=${page}`);
    if (!res.ok) await throwApiError(res, 'Failed to load the personality traits');
    const body = (await res.json()) as PersonalityTraitPage;
    traits.push(...body.results);
    if (!body.next) return traits;
  }
}

/** One NPC as its owner reads it (404 for an NPC the viewer may not manage). */
export async function fetchNpcDetail(entryId: number): Promise<NpcDetail> {
  const res = await apiFetch(`/api/roster/npcs/${entryId}/`);
  if (!res.ok) await throwApiError(res, 'Failed to load the NPC');
  return (await res.json()) as NpcDetail;
}

/**
 * The preference list to save: the saved rows, less the ones the GM removed, with the
 * GM's own lines on top (a typed line replaces a saved one for the same trait).
 */
export function mergePreferences(
  saved: SavedPreference[],
  removedTraits: number[],
  typed: PreferenceLine[]
): PreferenceLine[] {
  const typedTraits = new Set(typed.map((line) => line.trait));
  const kept = saved
    .filter((row) => !removedTraits.includes(row.trait_id) && !typedTraits.has(row.trait_id))
    .map((row) => ({ trait: row.trait_id, valence: row.valence }));
  return [...kept, ...typed];
}

/** The sheet behind a roster entry (the sheet id is the character id). */
export async function fetchSheetIdForEntry(entryId: number): Promise<number> {
  const entry = await fetchRosterEntry(entryId);
  return entry.character.id;
}

// ---------------------------------------------------------------------------
// Powers (typed in the form, applied after the mint)
// ---------------------------------------------------------------------------

export type PowerOptions = Schemas['NPCPowerOptions'];

/** `GET /api/roster/npcs/power-options/`: what the form's Powers pickers offer so far. */
export async function fetchNpcPowerOptions(pick: {
  path: string;
  tradition: string;
  gift: string;
}): Promise<PowerOptions> {
  const params = new URLSearchParams();
  if (pick.path) params.set('path', pick.path);
  if (pick.tradition) params.set('tradition', pick.tradition);
  if (pick.gift) params.set('gift', pick.gift);
  const res = await apiFetch(`/api/roster/npcs/power-options/?${params}`);
  if (!res.ok) await throwApiError(res, 'Failed to load the powers choices');
  return (await res.json()) as PowerOptions;
}

/** What the GM picked under Powers; ids are held as the pickers' strings. */
export interface PowersDraft {
  path: string;
  /** The path's level, or ''. */
  level: string;
  tradition: string;
  gift: string;
  techniques: number[];
  resonance: string;
  animaStat: string;
  animaSkill: string;
  /** Stat and skill overrides by trait id; '' is untouched. */
  stats: Record<string, string>;
  skills: Record<string, string>;
}

export const EMPTY_POWERS: PowersDraft = {
  path: '',
  level: '',
  tradition: '',
  gift: '',
  techniques: [],
  resonance: '',
  animaStat: '',
  animaSkill: '',
  stats: {},
  skills: {},
};

/** Magic is granted only once every pick it needs is made, as Grant magic requires. */
export function magicComplete(powers: PowersDraft): boolean {
  return Boolean(
    powers.tradition &&
      powers.gift &&
      powers.techniques.length > 0 &&
      powers.resonance &&
      powers.animaStat &&
      powers.animaSkill
  );
}

function filledValues(values: Record<string, string>): Record<string, number> {
  return Object.fromEntries(
    Object.entries(values)
      .filter(([, text]) => text.trim() !== '')
      .map(([id, text]) => [id, Number(text)])
  );
}

// ---------------------------------------------------------------------------
// Writes
// ---------------------------------------------------------------------------

/** Mint through `mint_story_npc` (a template when asked); answers the new entry's id. */
export async function mintNpc(
  characterId: number,
  kwargs: { name: string; description: string; preset: string; asTemplate: boolean }
): Promise<number> {
  const sent: Record<string, string | boolean> = { name: kwargs.name };
  if (kwargs.description) sent.description = kwargs.description;
  if (kwargs.preset) sent.preset = kwargs.preset;
  if (kwargs.asTemplate) sent.as_template = true;
  const result = await postDispatchAction(characterId, {
    ref: { backend: 'registry', registry_key: 'mint_story_npc' },
    kwargs: sent,
  });
  if (isDispatchFailure(result)) throw new Error(result.message ?? 'The NPC was not created.');
  const entryId = result.data?.roster_entry_id;
  if (typeof entryId !== 'number') throw new Error('The NPC was not created.');
  return entryId;
}

/** Put a story NPC into the scene's room through `place_npc_in_scene`. */
export async function placeNpcInScene(
  characterId: number,
  entryId: number,
  sceneId: number
): Promise<void> {
  const result = await postDispatchAction(characterId, {
    ref: { backend: 'registry', registry_key: 'place_npc_in_scene' },
    kwargs: { roster_entry_id: entryId, scene_id: sceneId },
  });
  if (isDispatchFailure(result)) throw new Error(result.message ?? 'Not added to the scene.');
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
    { source_entry: sourceEntryId, section } satisfies CopySectionRequest,
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
    { name, as_template: asTemplate } satisfies CopyAsNewRequest,
    'The copy was not made.'
  );
  const body = (await res.json()) as Schemas['CreatedNPC'];
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
    } satisfies RegardRequest,
    'Who they favor and oppose was not saved.'
  );
}

export async function putNpcPreferences(entryId: number, lines: PreferenceLine[]): Promise<void> {
  await sendNpc(
    `/api/roster/npcs/${entryId}/preferences/`,
    'PUT',
    { preferences: lines } satisfies PreferencesRequest,
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
  /** Copied preference rows the GM removed before saving, by trait id. */
  removedPreferences: number[];
  /** Lending settings and notes the GM changed. */
  settings: NpcSettingsPatch;
  /** Typed Powers, applied on top of a stat block or a Powers copy. */
  powers?: PowersDraft;
}

export const IDENTITY_KEYS = [
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
export const BACKGROUND_KEYS = ['concept', 'protect', 'fear', 'never_do', 'background'] as const;

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
    // Copied regard and preferences are kept and the GM's lines merge on top, so
    // "Start from" fills these two even when the GM adds lines of their own.
    case 'regard':
    case 'preferences':
      return false;
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

/** Each section's name as the form shows it, for a failed step's message. */
export const SECTION_TITLES: Record<NpcSection, string> = {
  identity: 'Who they are',
  description: 'Description',
  background: 'Background and drives',
  powers: 'Powers',
  regard: 'Who they favor and oppose',
  preferences: 'What works on them',
};

/** A step after the mint failed: the NPC exists, and the steps can be run again. */
export class NpcStepError extends Error {
  constructor(
    readonly step: string,
    failure: unknown
  ) {
    super(failure instanceof Error ? failure.message : step);
  }
}

async function step(label: string, run: () => Promise<void>): Promise<void> {
  try {
    await run();
  } catch (error) {
    throw new NpcStepError(label, error);
  }
}

function pick(sheet: StaffEditBody, keys: readonly string[]): StaffEditBody {
  const all = sheet as Record<string, unknown>;
  return Object.fromEntries(
    keys.filter((key) => all[key] !== undefined).map((key) => [key, all[key]])
  ) as StaffEditBody;
}

/**
 * Mint, copy, then write what was filled in on top. Answers the new roster entry's id.
 *
 * With ``mintedId`` (an NPC an earlier attempt already minted) the mint is skipped and
 * every later step runs again (each one replaces or upserts, so running it twice is
 * safe). A failed later step throws ``NpcStepError`` naming it. With ``sceneId`` the
 * NPC is put into that scene last; a template never is.
 *
 * The typed description rides the mint unless the description is being copied, in
 * which case it is written after the copy so it lands on top. On a retry (the mint
 * already done) it is written the same way, so an edit made since the mint is kept.
 */
export interface CreateNpcOptions {
  /** An NPC an earlier attempt already minted; the mint is skipped. */
  mintedId?: number | null;
  /** Hears the id the moment the mint succeeds. */
  onMinted?: (entryId: number) => void;
  /** Mint a template instead of an NPC the GM holds. */
  asTemplate?: boolean;
  /** The scene to put the new NPC into, last. */
  sceneId?: number | null;
}

/**
 * Typed Powers, in the order NpcPowersPanel's editors take them: path, magic, stats,
 * skills. Each step is safe to run again (a granted gift is not granted twice).
 */
async function applyPowers(entryId: number, powers: PowersDraft): Promise<void> {
  const stats = filledValues(powers.stats);
  const skills = filledValues(powers.skills);
  const wantsMagic = magicComplete(powers);
  const nothingTyped =
    !powers.path &&
    !powers.level &&
    !wantsMagic &&
    Object.keys(stats).length === 0 &&
    Object.keys(skills).length === 0;
  if (nothingTyped) return;
  let sheetId: number | null = null;
  const sheet = async () => (sheetId ??= await fetchSheetIdForEntry(entryId));
  if (powers.path) {
    await step(
      'saving the path',
      async () =>
        void (await runStaffRowAction(await sheet(), {
          path: 'staff-path',
          method: 'PATCH',
          body: { path: Number(powers.path) },
        }))
    );
  }
  if (powers.level) {
    await step(
      'saving the path level',
      async () =>
        void (await runStaffRowAction(await sheet(), {
          path: 'staff-path',
          method: 'PATCH',
          body: { level: Number(powers.level) },
        }))
    );
  }
  if (wantsMagic) {
    await step('granting magic', async () => {
      const sid = await sheet();
      const held = (await fetchCharacterSheet(sid)).staff_edit?.rows.has_gift;
      if (held) return;
      await runStaffRowAction(sid, {
        path: 'staff-magic',
        method: 'POST',
        body: {
          tradition: Number(powers.tradition),
          gift: Number(powers.gift),
          techniques: powers.techniques,
          resonance: Number(powers.resonance),
          anima_stat: Number(powers.animaStat),
          anima_skill: Number(powers.animaSkill),
        },
      });
    });
  }
  if (Object.keys(stats).length > 0) {
    await step(
      'saving the stats',
      async () =>
        void (await runStaffRowAction(await sheet(), {
          path: 'staff-stats',
          method: 'PATCH',
          body: { stats },
        }))
    );
  }
  if (Object.keys(skills).length > 0) {
    await step(
      'saving the skills',
      async () =>
        void (await runStaffRowAction(await sheet(), {
          path: 'staff-skills',
          method: 'PATCH',
          body: { skills },
        }))
    );
  }
}

async function saveDraftPreferences(
  id: number,
  draft: NpcFormDraft,
  preferencesCopied: boolean
): Promise<void> {
  if (draft.preferences.length === 0 && !(preferencesCopied && draft.removedPreferences.length > 0))
    return;
  await step('saving What works on them', async () => {
    // A copy wrote the source's rows; read them back so the save keeps them.
    const saved = preferencesCopied ? (await fetchNpcDetail(id)).preferences : [];
    await putNpcPreferences(
      id,
      mergePreferences(saved, draft.removedPreferences, draft.preferences)
    );
  });
}

export async function createNpc(
  characterId: number,
  draft: NpcFormDraft,
  {
    mintedId = null,
    onMinted = () => {},
    asTemplate = false,
    sceneId = null,
  }: CreateNpcOptions = {}
): Promise<number> {
  const copies = plannedCopies(draft);
  const descriptionCopied = copies.some(([section]) => section === 'description');
  // Written after the mint rather than with it: copied over, or minted on an earlier try.
  const descriptionAfterMint = descriptionCopied || mintedId !== null;
  let entryId = mintedId;
  if (entryId === null) {
    entryId = await mintNpc(characterId, {
      name: draft.name.trim(),
      description: descriptionCopied ? '' : draft.description,
      preset: draft.preset,
      asTemplate,
    });
    onMinted(entryId);
  }
  const id = entryId;
  for (const [section, source] of copies) {
    await step(`copying ${SECTION_TITLES[section]}`, () => copyNpcSection(id, source, section));
  }
  const sheetWrites: [string, StaffEditBody][] = [
    ['saving Who they are', pick(draft.sheet, IDENTITY_KEYS)],
    [
      'saving the description',
      descriptionAfterMint && draft.description ? { description: draft.description } : {},
    ],
    ['saving Background and drives', pick(draft.sheet, BACKGROUND_KEYS)],
  ];
  let sheetId: number | null = null;
  for (const [label, body] of sheetWrites) {
    if (Object.keys(body).length === 0) continue;
    await step(label, async () => {
      const sid = sheetId ?? (await fetchSheetIdForEntry(id));
      sheetId = sid;
      await patchStaffEdit(sid, body);
    });
  }
  if (draft.powers) await applyPowers(id, draft.powers);
  for (const line of draft.regard) {
    await step('saving Who they favor and oppose', () => putNpcRegard(id, line));
  }
  const preferencesCopied = copies.some(([section]) => section === 'preferences');
  await saveDraftPreferences(id, draft, preferencesCopied);
  if (Object.keys(draft.settings).length > 0) {
    await step('saving the notes and lending', () => patchNpcSettings(id, draft.settings));
  }
  if (sceneId !== null && !asTemplate) {
    await step('adding them to the scene', () => placeNpcInScene(characterId, id, sceneId));
  }
  return id;
}

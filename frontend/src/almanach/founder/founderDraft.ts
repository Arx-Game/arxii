/**
 * Founder Almanach browser draft (#3983 Plan B Task 4) — the founder's whole
 * house-claim journey (Seat, House, Family, Land, Estate) kept in
 * localStorage as the player fills it in across the founder chapters (Tasks
 * 5-6 build the House/Family/Land/Estate forms on top of this state; this
 * shell just needs somewhere durable to put the picks). Mirrors
 * `world-builder/document/useDraft.ts`'s localStorage discipline: every
 * read/write is try/catch wrapped, so private browsing, a storage quota, or
 * disabled storage degrade to "nothing remembered," never a crash — the
 * page must still render.
 */
import { useEffect, useState } from 'react';

import type { HouseClaimPayload, HouseTemplateOption } from '@/character-creation/api';
import type { ClaimKinRelation } from '@/character-creation/types';

export interface FounderKin {
  key: string;
  name: string;
  relation: ClaimKinRelation;
  gender_id: number | null;
  age: number | null;
  is_deceased: boolean;
  born_into_id: number | null;
  born_into_name: string;
  is_household: boolean;
}

export interface FounderLand {
  title_id: number;
  land_name: string;
  description: string;
  hall_name: string;
  land_shape_names: string[];
}

export interface FounderDraft {
  realm_id: number | null;
  title_id: number | null;
  template_id: number | null;
  house_name: string;
  words: string;
  colors: string;
  sigil_description: string;
  backstory: string;
  aspect_picks: Record<number, number[]>;
  principles: Record<string, number>;
  founder_relation: ClaimKinRelation;
  founder_is_heir: boolean;
  kin: FounderKin[];
  lands: Record<number, FounderLand>;
  estate_name: string;
  estate_description: string;
}

function emptyDraft(): FounderDraft {
  return {
    realm_id: null,
    title_id: null,
    template_id: null,
    house_name: '',
    words: '',
    colors: '',
    sigil_description: '',
    backstory: '',
    aspect_picks: {},
    principles: {},
    founder_relation: 'head',
    founder_is_heir: true,
    kin: [],
    lands: {},
    estate_name: '',
    estate_description: '',
  };
}

function draftKey(draftId: number): string {
  return `almanach-founder-${draftId}`;
}

function readFounderDraft(draftId: number): FounderDraft {
  try {
    const raw = window.localStorage.getItem(draftKey(draftId));
    if (!raw) return emptyDraft();
    return { ...emptyDraft(), ...(JSON.parse(raw) as Partial<FounderDraft>) };
  } catch {
    return emptyDraft();
  }
}

function writeFounderDraft(draftId: number, draft: FounderDraft): void {
  try {
    window.localStorage.setItem(draftKey(draftId), JSON.stringify(draft));
  } catch {
    // Storage unavailable — the draft is a convenience, never a requirement.
  }
}

function removeFounderDraft(draftId: number): void {
  try {
    window.localStorage.removeItem(draftKey(draftId));
  } catch {
    // Storage unavailable — nothing to clean up.
  }
}

let kinSeq = 0;
/** A stable per-row key for a freshly added kin entry — not sent to the
 * server (`toClaimPayload` drops it), just a React list key / edit handle. */
function nextKinKey(): string {
  kinSeq += 1;
  return `kin-${Date.now()}-${kinSeq}`;
}

export interface UseFounderDraftResult {
  draft: FounderDraft;
  set: <K extends keyof FounderDraft>(k: K, v: FounderDraft[K]) => void;
  addKin: (k: Omit<FounderKin, 'key'>) => void;
  updateKin: (key: string, patch: Partial<FounderKin>) => void;
  removeKin: (key: string) => void;
  setLand: (titleId: number, patch: Partial<FounderLand>) => void;
  reset: () => void;
}

/** `remoteValue`-free version of `useDraft` (`world-builder/document/
 * useDraft.ts`) — there's no server value to fall back to; a fresh draft
 * starts empty and is built up entirely client-side until the review step
 * (Task 6) submits it. */
export function useFounderDraft(draftId: number): UseFounderDraftResult {
  const [draft, setDraftState] = useState<FounderDraft>(() => readFounderDraft(draftId));

  useEffect(() => {
    setDraftState(readFounderDraft(draftId));
    // Only re-sync when the draft identity changes.
  }, [draftId]);

  const persist = (next: FounderDraft) => {
    setDraftState(next);
    writeFounderDraft(draftId, next);
  };

  const set = <K extends keyof FounderDraft>(k: K, v: FounderDraft[K]) => {
    persist({ ...draft, [k]: v });
  };

  const addKin = (k: Omit<FounderKin, 'key'>) => {
    persist({ ...draft, kin: [...draft.kin, { ...k, key: nextKinKey() }] });
  };

  const updateKin = (key: string, patch: Partial<FounderKin>) => {
    persist({
      ...draft,
      kin: draft.kin.map((kin) => (kin.key === key ? { ...kin, ...patch } : kin)),
    });
  };

  const removeKin = (key: string) => {
    persist({ ...draft, kin: draft.kin.filter((kin) => kin.key !== key) });
  };

  const setLand = (titleId: number, patch: Partial<FounderLand>) => {
    const existing: FounderLand = draft.lands[titleId] ?? {
      title_id: titleId,
      land_name: '',
      description: '',
      hall_name: '',
      land_shape_names: [],
    };
    persist({ ...draft, lands: { ...draft.lands, [titleId]: { ...existing, ...patch } } });
  };

  const reset = () => {
    removeFounderDraft(draftId);
    setDraftState(emptyDraft());
  };

  return { draft, set, addKin, updateKin, removeKin, setLand, reset };
}

/**
 * The founder's whole draft as the nested claim-submission payload (Plan B
 * Task 3's `POST /api/character-creation/drafts/{id}/house-claim/` body,
 * Task 6's review step calls this). `FounderKin` carries no `basis` field
 * yet — Task 4's shell has no UI for a household position's basis text —
 * so every kin row submits `basis: ''` until a later task adds one.
 */
export function toClaimPayload(d: FounderDraft, template: HouseTemplateOption): HouseClaimPayload {
  return {
    title: d.title_id ?? 0,
    template: template.id,
    house_name: d.house_name,
    backstory: d.backstory,
    words: d.words,
    colors: d.colors,
    sigil_description: d.sigil_description,
    aspects: Object.entries(d.aspect_picks).map(([definitionId, options]) => ({
      definition: Number(definitionId),
      options,
    })),
    mercy: d.principles.mercy ?? 0,
    method: d.principles.method ?? 0,
    status: d.principles.status ?? 0,
    change: d.principles.change ?? 0,
    allegiance: d.principles.allegiance ?? 0,
    power: d.principles.power ?? 0,
    founder_relation: d.founder_relation,
    founder_is_heir: d.founder_is_heir,
    kin: d.kin.map((kin) => ({
      name: kin.name,
      relation: kin.relation,
      gender: kin.gender_id,
      age: kin.age,
      is_deceased: kin.is_deceased,
      born_into: kin.born_into_id,
      basis: '',
      is_household: kin.is_household,
    })),
    lands: Object.values(d.lands).map((land) => ({
      title: land.title_id,
      land_name: land.land_name,
      description: land.description,
      hall_name: land.hall_name,
      land_shapes: land.land_shape_names,
    })),
    estate: { name: d.estate_name, description: d.estate_description },
  };
}

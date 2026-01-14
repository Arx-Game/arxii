/**
 * Character Creation API functions
 */

import { apiFetch } from '@/evennia_replacements/api';
import type {
  Beginnings,
  CGPointBudget,
  CGPointsBreakdown,
  CharacterDraft,
  CharacterDraftUpdate,
  Family,
  FamilyMember,
  FamilyTree,
  GenderOption,
  Species,
  SpeciesOption,
  StartingArea,
} from './types';

const BASE_URL = '/api/character-creation';
const ROSTER_URL = '/api/roster';

export async function getStartingAreas(): Promise<StartingArea[]> {
  const res = await apiFetch(`${BASE_URL}/starting-areas/`);
  if (!res.ok) {
    throw new Error('Failed to load starting areas');
  }
  return res.json();
}

export async function getBeginnings(areaId: number): Promise<Beginnings[]> {
  const res = await apiFetch(`${BASE_URL}/beginnings/?starting_area=${areaId}`);
  if (!res.ok) {
    throw new Error('Failed to load beginnings options');
  }
  return res.json();
}

export async function getGenders(): Promise<GenderOption[]> {
  const res = await apiFetch(`${BASE_URL}/genders/`);
  if (!res.ok) {
    throw new Error('Failed to load gender options');
  }
  return res.json();
}

export async function getSpecies(areaId: number, heritageId?: number): Promise<Species[]> {
  const params = new URLSearchParams({ area_id: areaId.toString() });
  if (heritageId) {
    params.append('heritage_id', heritageId.toString());
  }
  const res = await apiFetch(`${BASE_URL}/species/?${params}`);
  if (!res.ok) {
    throw new Error('Failed to load species');
  }
  return res.json();
}

export async function getFamilies(areaId: number): Promise<Family[]> {
  const res = await apiFetch(`${BASE_URL}/families/?area_id=${areaId}`);
  if (!res.ok) {
    throw new Error('Failed to load families');
  }
  return res.json();
}

export async function getDraft(): Promise<CharacterDraft | null> {
  const res = await apiFetch(`${BASE_URL}/drafts/`);
  if (!res.ok) {
    throw new Error('Failed to load draft');
  }
  const drafts = await res.json();

  // User can only have one draft, return first or null
  if (drafts.length > 1 && import.meta.env.DEV) {
    console.warn(
      `⚠️ Multiple drafts found (${drafts.length}). User should only have one draft.`,
      drafts
    );
  }

  return drafts.length > 0 ? drafts[0] : null;
}

export async function createDraft(): Promise<CharacterDraft> {
  const res = await apiFetch(`${BASE_URL}/drafts/`, {
    method: 'POST',
  });
  if (!res.ok) {
    throw new Error('Failed to create draft');
  }
  return res.json();
}

export async function updateDraft(
  draftId: number,
  data: CharacterDraftUpdate
): Promise<CharacterDraft> {
  const res = await apiFetch(`${BASE_URL}/drafts/${draftId}/`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    throw new Error('Failed to update draft');
  }
  return res.json();
}

export async function deleteDraft(draftId: number): Promise<void> {
  const res = await apiFetch(`${BASE_URL}/drafts/${draftId}/`, {
    method: 'DELETE',
  });
  if (!res.ok) {
    throw new Error('Failed to delete draft');
  }
}

export async function submitDraft(
  draftId: number
): Promise<{ character_id: number; message: string }> {
  const res = await apiFetch(`${BASE_URL}/drafts/${draftId}/submit/`, {
    method: 'POST',
  });
  if (!res.ok) {
    throw new Error('Failed to submit draft');
  }
  return res.json();
}

export async function addToRoster(
  draftId: number
): Promise<{ character_id: number; message: string }> {
  const res = await apiFetch(`${BASE_URL}/drafts/${draftId}/add-to-roster/`, {
    method: 'POST',
  });
  if (!res.ok) {
    throw new Error('Failed to add to roster');
  }
  return res.json();
}

export async function canCreateCharacter(): Promise<{ can_create: boolean; reason: string }> {
  const res = await apiFetch(`${BASE_URL}/can-create/`);
  if (!res.ok) {
    throw new Error('Failed to check creation eligibility');
  }
  return res.json();
}

// NEW: Species Options (species-area combinations with costs)
export async function getSpeciesOptions(areaId: number): Promise<SpeciesOption[]> {
  const res = await apiFetch(`${BASE_URL}/species-options/?starting_area=${areaId}`);
  if (!res.ok) {
    throw new Error('Failed to load species options');
  }
  return res.json();
}

export async function getSpeciesOptionDetail(id: number): Promise<SpeciesOption> {
  const res = await apiFetch(`${BASE_URL}/species-options/${id}/`);
  if (!res.ok) {
    throw new Error('Failed to load species option');
  }
  return res.json();
}

// NEW: CG Points Budget
export async function getCGPointBudget(): Promise<CGPointBudget> {
  const res = await apiFetch(`${BASE_URL}/cg-budgets/`);
  if (!res.ok) {
    throw new Error('Failed to load CG point budget');
  }
  const budgets = await res.json();
  return budgets.length > 0
    ? budgets[0]
    : { id: 0, name: 'Default', starting_points: 100, is_active: true };
}

export async function getDraftCGPoints(draftId: number): Promise<CGPointsBreakdown> {
  const res = await apiFetch(`${BASE_URL}/drafts/${draftId}/cg-points/`);
  if (!res.ok) {
    throw new Error('Failed to load CG points breakdown');
  }
  return res.json();
}

// NEW: Family Tree Management
export async function getFamiliesWithOpenPositions(areaId?: number): Promise<Family[]> {
  const params = new URLSearchParams({ has_open_positions: 'true' });
  if (areaId) {
    params.append('area_id', areaId.toString());
  }
  const res = await apiFetch(`${ROSTER_URL}/families/?${params}`);
  if (!res.ok) {
    throw new Error('Failed to load families');
  }
  return res.json();
}

export async function getFamilyTree(familyId: number): Promise<FamilyTree> {
  const res = await apiFetch(`${ROSTER_URL}/families/${familyId}/tree/`);
  if (!res.ok) {
    throw new Error('Failed to load family tree');
  }
  return res.json();
}

export async function createFamily(data: {
  name: string;
  family_type: 'commoner' | 'noble';
  description: string;
  origin_realm?: number;
}): Promise<Family> {
  const res = await apiFetch(`${ROSTER_URL}/families/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    throw new Error('Failed to create family');
  }
  return res.json();
}

export async function createFamilyMember(data: {
  family_id: number;
  member_type: 'placeholder' | 'npc';
  name: string;
  description?: string;
  age?: number;
  mother_id?: number | null;
  father_id?: number | null;
}): Promise<FamilyMember> {
  const res = await apiFetch(`${ROSTER_URL}/family-members/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    throw new Error('Failed to create family member');
  }
  return res.json();
}

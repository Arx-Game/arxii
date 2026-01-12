/**
 * Character Creation API functions
 */

import { apiFetch } from '@/evennia_replacements/api';
import type { CharacterDraft, CharacterDraftUpdate, Family, Species, StartingArea } from './types';

const BASE_URL = '/api/character-creation';

export async function getStartingAreas(): Promise<StartingArea[]> {
  const res = await apiFetch(`${BASE_URL}/starting-areas/`);
  if (!res.ok) {
    throw new Error('Failed to load starting areas');
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

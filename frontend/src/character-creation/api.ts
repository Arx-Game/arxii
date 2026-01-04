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
  const res = await apiFetch(`${BASE_URL}/draft/`);
  if (res.status === 404) {
    return null;
  }
  if (!res.ok) {
    throw new Error('Failed to load draft');
  }
  return res.json();
}

export async function createDraft(): Promise<CharacterDraft> {
  const res = await apiFetch(`${BASE_URL}/draft/`, {
    method: 'POST',
  });
  if (!res.ok) {
    throw new Error('Failed to create draft');
  }
  return res.json();
}

export async function updateDraft(data: CharacterDraftUpdate): Promise<CharacterDraft> {
  const res = await apiFetch(`${BASE_URL}/draft/`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    throw new Error('Failed to update draft');
  }
  return res.json();
}

export async function deleteDraft(): Promise<void> {
  const res = await apiFetch(`${BASE_URL}/draft/`, {
    method: 'DELETE',
  });
  if (!res.ok) {
    throw new Error('Failed to delete draft');
  }
}

export async function submitDraft(): Promise<{ character_id: number; message: string }> {
  const res = await apiFetch(`${BASE_URL}/draft/submit/`, {
    method: 'POST',
  });
  if (!res.ok) {
    throw new Error('Failed to submit draft');
  }
  return res.json();
}

export async function addToRoster(): Promise<{ character_id: number; message: string }> {
  const res = await apiFetch(`${BASE_URL}/draft/add-to-roster/`, {
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

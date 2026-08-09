/**
 * API functions for the deliberate skill training surface (#3045).
 *
 * All writes dispatch through `ManageTrainingAction` server-side (the same
 * seam telnet's `training` command uses) — see world.skills.views.
 */

import { apiFetch } from '@/evennia_replacements/api';
import { readErrorDetail } from '@/lib/errors';
import type {
  ManageTrainingAddRequest,
  PatchedManageTrainingUpdateRequest,
  SkillListItem,
  TrainingAllocation,
  TrainingAllocationList,
} from './types';

export async function fetchSkillsCatalog(): Promise<SkillListItem[]> {
  const res = await apiFetch('/api/skills/skills/');
  if (!res.ok) await readErrorDetail(res, 'Failed to load the skill catalog');
  return res.json() as Promise<SkillListItem[]>;
}

export async function fetchTrainingAllocations(): Promise<TrainingAllocationList> {
  const res = await apiFetch('/api/skills/training-allocations/');
  if (!res.ok) await readErrorDetail(res, 'Failed to load training allocations');
  return res.json() as Promise<TrainingAllocationList>;
}

export async function createTrainingAllocation(
  body: ManageTrainingAddRequest
): Promise<TrainingAllocation> {
  const res = await apiFetch('/api/skills/training-allocations/', {
    method: 'POST',
    body: JSON.stringify(body),
  });
  if (!res.ok) await readErrorDetail(res, 'Failed to allocate training');
  return res.json() as Promise<TrainingAllocation>;
}

export async function updateTrainingAllocation(
  id: number,
  body: PatchedManageTrainingUpdateRequest
): Promise<TrainingAllocation> {
  const res = await apiFetch(`/api/skills/training-allocations/${id}/`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  });
  if (!res.ok) await readErrorDetail(res, 'Failed to update training allocation');
  return res.json() as Promise<TrainingAllocation>;
}

export async function deleteTrainingAllocation(id: number): Promise<void> {
  const res = await apiFetch(`/api/skills/training-allocations/${id}/`, {
    method: 'DELETE',
  });
  if (!res.ok) await readErrorDetail(res, 'Failed to remove training allocation');
}

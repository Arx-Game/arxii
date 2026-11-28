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
  MentoringAnswerResult,
  MentoringList,
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

export async function fetchMentoring(): Promise<MentoringList> {
  const res = await apiFetch('/api/skills/training-allocations/mentoring/');
  if (!res.ok) await readErrorDetail(res, 'Failed to load mentoring requests');
  return res.json() as Promise<MentoringList>;
}

export type MentoringAnswer = 'accept' | 'decline' | 'stop';

/** A mentor answers one request, or ends one she teaches: the sentence comes back as `detail`. */
export async function answerMentoring(
  allocationId: number,
  answer: MentoringAnswer
): Promise<MentoringAnswerResult> {
  const res = await apiFetch(
    `/api/skills/training-allocations/${allocationId}/${answer}-mentoring/`,
    { method: 'POST' }
  );
  if (!res.ok) await readErrorDetail(res, 'Could not answer the mentoring request');
  return res.json() as Promise<MentoringAnswerResult>;
}

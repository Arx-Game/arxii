/**
 * API functions for the goal-log affordance (#3045).
 *
 * `world.goals.views.CharacterGoalViewSet` / `GoalJournalViewSet` resolve the
 * acting character via the `X-Character-ID` header
 * (`web.api.mixins.CharacterContextMixin`) — same contract as
 * `magic/api.ts`'s Motif style / technique progress calls.
 */

import { apiFetch } from '@/evennia_replacements/api';
import { readErrorDetail } from '@/lib/errors';
import type { CreateGoalJournalRequest, GoalJournalEntry, MyGoalsResponse } from './types';

function characterHeaders(characterId: number): HeadersInit {
  return { 'X-Character-ID': String(characterId) };
}

export async function fetchMyGoals(characterId: number): Promise<MyGoalsResponse> {
  const res = await apiFetch('/api/goals/my-goals/', { headers: characterHeaders(characterId) });
  if (!res.ok) await readErrorDetail(res, 'Failed to load goals');
  return res.json() as Promise<MyGoalsResponse>;
}

export async function createGoalJournalEntry(
  characterId: number,
  body: CreateGoalJournalRequest
): Promise<GoalJournalEntry> {
  const res = await apiFetch('/api/goals/journals/', {
    method: 'POST',
    headers: characterHeaders(characterId),
    body: JSON.stringify(body),
  });
  if (!res.ok) await readErrorDetail(res, 'Failed to log goal progress');
  return res.json() as Promise<GoalJournalEntry>;
}

/**
 * Stewarded beings API (#4333 slice 4): the table page's Beings tab.
 *
 * A being a table stewards is written by the table's GM here (pledge types,
 * answers, sacrifice lines), and its closed pledges are answered from the
 * steward-prompts panel. Server: world.worship.steward_views.
 */

import { apiFetch } from '@/evennia_replacements/api';
import { throwApiError } from '@/lib/errors';
import type {
  Paginated,
  StewardAnswer,
  StewardAnswerWriteBody,
  StewardedBeing,
  StewardPledge,
  StewardPledgeWriteBody,
  StewardPrompt,
  StewardSacrificeLineWriteBody,
  StewardSendBody,
} from './types';

const BASE = '/api/worship';

function jsonInit(method: string, body: unknown): RequestInit {
  return { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) };
}

export async function getStewardedBeings(tableId: number): Promise<Paginated<StewardedBeing>> {
  const res = await apiFetch(`${BASE}/stewarded-beings/?table=${tableId}`);
  if (!res.ok) await throwApiError(res, "Failed to load the table's beings");
  return res.json() as Promise<Paginated<StewardedBeing>>;
}

export async function getStewardAnswers(beingId: number): Promise<Paginated<StewardAnswer>> {
  const res = await apiFetch(`${BASE}/steward-answers/?being=${beingId}&page_size=100`);
  if (!res.ok) await throwApiError(res, 'Failed to load the answers');
  return res.json() as Promise<Paginated<StewardAnswer>>;
}

export async function savePledge(
  body: StewardPledgeWriteBody,
  pledgeId?: number
): Promise<StewardPledge> {
  const res = pledgeId
    ? await apiFetch(`${BASE}/steward-pledges/${pledgeId}/`, jsonInit('PATCH', body))
    : await apiFetch(`${BASE}/steward-pledges/`, jsonInit('POST', body));
  if (!res.ok) await throwApiError(res, 'Failed to save the pledge type');
  return res.json() as Promise<StewardPledge>;
}

export async function saveAnswer(
  body: StewardAnswerWriteBody,
  answerId?: number
): Promise<StewardAnswer> {
  const res = answerId
    ? await apiFetch(`${BASE}/steward-answers/${answerId}/`, jsonInit('PATCH', body))
    : await apiFetch(`${BASE}/steward-answers/`, jsonInit('POST', body));
  if (!res.ok) await throwApiError(res, 'Failed to save the answer');
  return res.json() as Promise<StewardAnswer>;
}

export async function saveSacrificeLine(
  body: StewardSacrificeLineWriteBody,
  lineId?: number
): Promise<void> {
  const res = lineId
    ? await apiFetch(`${BASE}/steward-sacrifice-lines/${lineId}/`, jsonInit('PATCH', body))
    : await apiFetch(`${BASE}/steward-sacrifice-lines/`, jsonInit('POST', body));
  if (!res.ok) await throwApiError(res, 'Failed to save the sacrifice line');
}

export async function getStewardPrompts(tableId: number): Promise<Paginated<StewardPrompt>> {
  const res = await apiFetch(`${BASE}/steward-prompts/?table=${tableId}`);
  if (!res.ok) await throwApiError(res, 'Failed to load the waiting answers');
  return res.json() as Promise<Paginated<StewardPrompt>>;
}

export async function sendStewardAnswer(
  promptId: number,
  body: StewardSendBody
): Promise<{ detail: string }> {
  const res = await apiFetch(`${BASE}/steward-prompts/${promptId}/answer/`, jsonInit('POST', body));
  if (!res.ok) await throwApiError(res, 'Failed to send the answer');
  return res.json() as Promise<{ detail: string }>;
}

export async function dismissStewardPrompt(promptId: number): Promise<{ detail: string }> {
  const res = await apiFetch(`${BASE}/steward-prompts/${promptId}/dismiss/`, jsonInit('POST', {}));
  if (!res.ok) await throwApiError(res, 'Failed to dismiss the prompt');
  return res.json() as Promise<{ detail: string }>;
}

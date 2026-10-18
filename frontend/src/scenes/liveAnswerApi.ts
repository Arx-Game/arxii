/**
 * Live answers (#4333 slice 5): a scene GM answers a rite performed in their
 * scene. Server: world.worship.live_views.
 */

import type { components } from '@/generated/api';
import { apiFetch } from '@/evennia_replacements/api';
import { throwApiError } from '@/lib/errors';

export type LivePrompt = components['schemas']['LivePrompt'];
export type LiveAnswerOption = components['schemas']['_LiveAnswer'];
export type LiveMiracleOption = components['schemas']['_LiveMiracle'];
export type LiveSendBody = components['schemas']['LiveSendRequest'];

const BASE = '/api/worship/live-answers';

function jsonInit(body: unknown): RequestInit {
  return {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  };
}

export async function getLivePrompt(promptId: number): Promise<LivePrompt> {
  const res = await apiFetch(`${BASE}/${promptId}/`);
  if (!res.ok) await throwApiError(res, 'Failed to load the rite');
  return res.json() as Promise<LivePrompt>;
}

export async function sendLiveAnswer(
  promptId: number,
  body: Partial<LiveSendBody>
): Promise<{ detail: string }> {
  const res = await apiFetch(`${BASE}/${promptId}/answer/`, jsonInit(body));
  if (!res.ok) await throwApiError(res, 'Failed to send the answer');
  return res.json() as Promise<{ detail: string }>;
}

export async function dismissLivePrompt(promptId: number): Promise<{ detail: string }> {
  const res = await apiFetch(`${BASE}/${promptId}/dismiss/`, jsonInit({}));
  if (!res.ok) await throwApiError(res, 'Failed to dismiss the prompt');
  return res.json() as Promise<{ detail: string }>;
}

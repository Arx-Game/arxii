/**
 * API calls for pre-scene RP capture (#3069 sub-item 4): the account-wide pending
 * consent inbox (accept/decline "may we fold your recent poses into this scene") and
 * the scene starter's truncate/"start from here" control.
 */

import { apiFetch } from '@/evennia_replacements/api';
import { readErrorDetail } from '@/lib/errors';
import type { PrecaptureConsentRequest, PrecapturePreviewInteraction, SceneDetail } from './types';

/** The scene's pre-scene-captured poses, oldest first — the truncate control's data. */
export async function fetchPrecapturedInteractions(
  sceneId: string
): Promise<PrecapturePreviewInteraction[]> {
  const res = await apiFetch(`/api/scenes/${sceneId}/precapture/`);
  if (!res.ok) await readErrorDetail(res, 'Failed to load captured poses');
  return res.json() as Promise<PrecapturePreviewInteraction[]>;
}

/** Account-wide pending precapture consent requests (server already scopes to `me`). */
export async function fetchPendingPrecaptureConsents(): Promise<PrecaptureConsentRequest[]> {
  const res = await apiFetch('/api/precapture-consent-requests/');
  if (!res.ok) await readErrorDetail(res, 'Failed to load pending capture requests');
  return res.json() as Promise<PrecaptureConsentRequest[]>;
}

export interface RespondPrecaptureConsentResult {
  attached_count: number;
  status: string;
}

export async function respondToPrecaptureConsent(
  requestId: number,
  accept: boolean
): Promise<RespondPrecaptureConsentResult> {
  const res = await apiFetch(`/api/precapture-consent-requests/${requestId}/respond/`, {
    method: 'POST',
    body: JSON.stringify({ accept }),
  });
  if (!res.ok) await readErrorDetail(res, 'Failed to respond to the capture request');
  return res.json() as Promise<RespondPrecaptureConsentResult>;
}

/** Starter/owner (or staff) drops every captured pose before `interactionId` ("start from here"). */
export async function truncatePrecapture(
  sceneId: string,
  interactionId: number
): Promise<SceneDetail> {
  const res = await apiFetch(`/api/scenes/${sceneId}/truncate-precapture/`, {
    method: 'POST',
    body: JSON.stringify({ interaction_id: interactionId }),
  });
  if (!res.ok) await readErrorDetail(res, 'Failed to truncate the captured poses');
  return res.json() as Promise<SceneDetail>;
}

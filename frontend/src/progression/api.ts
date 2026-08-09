/**
 * API functions for progression data.
 */

import { apiFetch } from '@/evennia_replacements/api';
import { readErrorDetail } from '@/lib/errors';
import type {
  AccountProgressionData,
  DuranceConveneResponse,
  DuranceStatus,
  PaginatedProgressionUnlockItemList,
  PurchaseUnlockRequest,
  PurchaseUnlockResponse,
} from './types';

export async function fetchAccountProgression(): Promise<AccountProgressionData> {
  const res = await apiFetch('/api/progression/account/');
  if (!res.ok) {
    throw new Error('Failed to load progression data');
  }
  return res.json();
}

export async function claimKudosForXP(
  claimCategoryId: number,
  amount: number
): Promise<AccountProgressionData> {
  const res = await apiFetch('/api/progression/claim-kudos/', {
    method: 'POST',
    body: JSON.stringify({ claim_category_id: claimCategoryId, amount }),
  });
  if (!res.ok) {
    const error = await res.json();
    throw new Error(error.detail || 'Failed to claim kudos');
  }
  return res.json();
}

// ---------------------------------------------------------------------------
// Unlock shop (#3045) — GET /api/progression/unlocks/, POST .../purchase/.
// Character is resolved server-side via the requester's puppeted character
// (ProgressionUnlockViewSet._resolve_puppet_sheet) — no X-Character-ID header.
// ---------------------------------------------------------------------------

export async function fetchProgressionUnlocks(
  unlockType?: 'class_level' | 'thread_xp_lock' | 'skill_breakthrough'
): Promise<PaginatedProgressionUnlockItemList> {
  const query = unlockType ? `?unlock_type=${unlockType}` : '';
  const res = await apiFetch(`/api/progression/unlocks/${query}`);
  if (!res.ok) await readErrorDetail(res, 'Failed to load unlocks');
  return res.json() as Promise<PaginatedProgressionUnlockItemList>;
}

export async function purchaseProgressionUnlock(
  body: PurchaseUnlockRequest
): Promise<PurchaseUnlockResponse> {
  const res = await apiFetch('/api/progression/unlocks/purchase/', {
    method: 'POST',
    body: JSON.stringify(body),
  });
  if (!res.ok) await readErrorDetail(res, 'Failed to purchase unlock');
  return res.json() as Promise<PurchaseUnlockResponse>;
}

// ---------------------------------------------------------------------------
// Durance readiness hub (#3045) — GET .../durance/status/, POST .../durance/convene/.
// Same puppet-resolution as the unlock shop; no X-Character-ID header.
// ---------------------------------------------------------------------------

export async function fetchDuranceStatus(): Promise<DuranceStatus> {
  const res = await apiFetch('/api/progression/durance/status/');
  if (!res.ok) await readErrorDetail(res, 'Failed to load Durance status');
  return res.json() as Promise<DuranceStatus>;
}

export async function conveneDurance(): Promise<DuranceConveneResponse> {
  const res = await apiFetch('/api/progression/durance/convene/', {
    method: 'POST',
    body: JSON.stringify({}),
  });
  if (!res.ok) await readErrorDetail(res, 'Failed to convene the Durance');
  return res.json() as Promise<DuranceConveneResponse>;
}

/**
 * POST /api/magic/rituals/sessions/{id}/accept/ — join a Durance session.
 *
 * Deliberately NOT `rituals/api.ts`'s `acceptRitualSession` (typed to the
 * `RitualSessionAccept` schema component, which is actually the mis-inferred
 * *request* shape — drf-spectacular has no `@extend_schema` on `accept()`, a
 * pre-existing gap). A site-convened Durance session auto-fires on accept
 * (#3045 — mirrors telnet's `ritual join` auto-fire), returning
 * `{detail, fired: true}` instead of a session-detail body once fired, so this
 * reads the response as a plain record rather than fighting that type.
 */
export async function joinDuranceSession(
  sessionId: number,
  participantKwargs: { testament: string; path_id?: number }
): Promise<{ detail?: string; fired?: boolean }> {
  const res = await apiFetch(`/api/magic/rituals/sessions/${sessionId}/accept/`, {
    method: 'POST',
    body: JSON.stringify({ participant_kwargs: participantKwargs }),
  });
  if (!res.ok) await readErrorDetail(res, 'Failed to join the Durance session');
  return res.json() as Promise<{ detail?: string; fired?: boolean }>;
}

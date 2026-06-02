/**
 * Sanctum API client (Plan 4 §F).
 *
 * GET /api/magic/sanctums/ — list Sanctums the active persona has standing in
 * POST /api/magic/sanctums/{id}/homecoming/ — grow the Sanctum's resonance reservoir
 * POST /api/magic/sanctums/{id}/purging/ — change the Sanctum's resonance type
 * POST /api/magic/sanctums/{id}/weave/ — bind a thread (PERSONAL_OWN / COVENANT / HELPER)
 * POST /api/magic/sanctums/{id}/sever/{thread_id}/ — soft-retire a Sanctum thread
 */

import { apiFetch } from '@/evennia_replacements/api';

import type {
  HomecomingRequest,
  HomecomingResult,
  PurgingRequest,
  PurgingResult,
  SanctumDetails,
  SanctumThread,
  WeaveRequest,
} from './sanctumTypes';

const SANCTUMS_URL = '/api/magic/sanctums';

function jsonHeaders(): HeadersInit {
  return { 'Content-Type': 'application/json' };
}

async function parseErrorDetail(res: Response, fallback: string): Promise<never> {
  let detail = fallback;
  try {
    const data = (await res.json()) as { detail?: string };
    if (typeof data.detail === 'string' && data.detail.trim()) {
      detail = data.detail;
    }
  } catch {
    // body wasn't JSON; keep the generic fallback
  }
  throw new Error(detail);
}

export async function getSanctums(): Promise<SanctumDetails[]> {
  const res = await apiFetch(`${SANCTUMS_URL}/`);
  if (!res.ok) throw new Error('Failed to load Sanctums');
  return res.json() as Promise<SanctumDetails[]>;
}

export async function performHomecoming(
  featureInstanceId: number,
  body: HomecomingRequest
): Promise<HomecomingResult> {
  const res = await apiFetch(`${SANCTUMS_URL}/${featureInstanceId}/homecoming/`, {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    await parseErrorDetail(res, 'Failed to perform Ritual of Homecoming');
  }
  return res.json() as Promise<HomecomingResult>;
}

export async function performPurging(
  featureInstanceId: number,
  body: PurgingRequest
): Promise<PurgingResult> {
  const res = await apiFetch(`${SANCTUMS_URL}/${featureInstanceId}/purging/`, {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    await parseErrorDetail(res, 'Failed to perform Ritual of Purging');
  }
  return res.json() as Promise<PurgingResult>;
}

export async function weaveSanctumThread(
  featureInstanceId: number,
  body: WeaveRequest
): Promise<SanctumThread> {
  const res = await apiFetch(`${SANCTUMS_URL}/${featureInstanceId}/weave/`, {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    await parseErrorDetail(res, 'Failed to weave Sanctum thread');
  }
  return res.json() as Promise<SanctumThread>;
}

export async function severSanctumThread(
  featureInstanceId: number,
  threadId: number
): Promise<void> {
  const res = await apiFetch(`${SANCTUMS_URL}/${featureInstanceId}/sever/${threadId}/`, {
    method: 'POST',
    headers: jsonHeaders(),
  });
  if (!res.ok) {
    await parseErrorDetail(res, 'Failed to sever Sanctum thread');
  }
}

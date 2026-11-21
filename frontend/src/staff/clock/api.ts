/**
 * The staff Game clock page's calls (#5248): the clock read, its four staff controls
 * (`world/game_clock/views.py::ClockViewSet`), the preview of a date change and the
 * history of changes (`ClockHistoryViewSet`).
 */

import { apiFetch } from '@/evennia_replacements/api';
import { throwApiError } from '@/lib/errors';
import type { PaginatedResponse } from '@/shared/types';
import type { AgeHandling, ClockHistoryRow, ClockJumpPreview, ClockState } from './types';

const BASE = '/api/clock';

async function post(path: string, body: object | undefined, fallback: string): Promise<void> {
  const res = await apiFetch(`${BASE}/${path}/`, {
    method: 'POST',
    ...(body ? { body: JSON.stringify(body) } : {}),
  });
  if (!res.ok) await throwApiError(res, fallback);
}

/** Throws an `ApiError` with status 503 when no clock exists yet. */
export async function fetchClock(): Promise<ClockState> {
  const res = await apiFetch(`${BASE}/`);
  if (!res.ok) await throwApiError(res, 'The clock could not be read.');
  return res.json();
}

export function pauseClock(): Promise<void> {
  return post('pause', undefined, 'The clock could not be paused.');
}

export function resumeClock(): Promise<void> {
  return post('unpause', undefined, 'The clock could not be resumed.');
}

export interface SetDateInput {
  ic_datetime: string;
  reason: string;
  age_handling: AgeHandling;
}

export function setClockDate(input: SetDateInput): Promise<void> {
  return post('adjust', input, 'The date could not be set.');
}

export function setClockSpeed(input: { ratio: number; reason: string }): Promise<void> {
  return post('ratio', input, 'The speed could not be changed.');
}

export async function fetchJumpPreview(icDatetime: string): Promise<ClockJumpPreview> {
  const params = new URLSearchParams({ ic_datetime: icDatetime });
  const res = await apiFetch(`${BASE}/adjust-preview/?${params.toString()}`);
  if (!res.ok) await throwApiError(res, 'That date could not be read.');
  return res.json();
}

export async function fetchClockHistory(page: number): Promise<PaginatedResponse<ClockHistoryRow>> {
  const params = new URLSearchParams({ page: String(page), page_size: String(HISTORY_PAGE_SIZE) });
  const res = await apiFetch(`${BASE}/history/?${params.toString()}`);
  if (!res.ok) await throwApiError(res, 'The changes could not be read.');
  return res.json();
}

export const HISTORY_PAGE_SIZE = 10;

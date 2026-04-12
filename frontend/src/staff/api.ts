/**
 * Staff Inbox API functions
 */

import { apiFetch } from '@/evennia_replacements/api';
import type { PaginatedResponse } from '@/shared/types';
import type {
  AccountHistory,
  BugReport,
  InboxResponse,
  PlayerFeedback,
  PlayerReport,
  SubmissionCategory,
  SubmissionStatus,
} from './types';

const INBOX_URL = '/api/staff-inbox';
const SUBMISSIONS_URL = '/api/player-submissions';

// =============================================================================
// Staff Inbox
// =============================================================================

export async function getStaffInbox(
  categories?: SubmissionCategory[],
  page?: number,
  pageSize?: number
): Promise<InboxResponse> {
  const params = new URLSearchParams();
  if (categories) {
    for (const cat of categories) {
      params.append('categories', cat);
    }
  }
  if (page) {
    params.append('page', page.toString());
  }
  if (pageSize) {
    params.append('page_size', pageSize.toString());
  }
  const qs = params.toString();
  const res = await apiFetch(`${INBOX_URL}/${qs ? `?${qs}` : ''}`);
  if (!res.ok) throw new Error('Failed to load staff inbox');
  return res.json();
}

export async function getAccountHistory(accountId: number): Promise<AccountHistory> {
  const res = await apiFetch(`${INBOX_URL}/accounts/${accountId}/history/`);
  if (!res.ok) throw new Error('Failed to load account history');
  return res.json();
}

export async function getOpenSubmissionCount(): Promise<number> {
  // Exclude character_application to avoid double-counting with the separate applications badge
  const params = new URLSearchParams();
  params.append('categories', 'player_feedback');
  params.append('categories', 'bug_report');
  params.append('categories', 'player_report');
  params.append('page_size', '1');
  const res = await apiFetch(`${INBOX_URL}/?${params}`);
  if (!res.ok) return 0;
  const data: InboxResponse = await res.json();
  return data.count;
}

// =============================================================================
// Player Feedback
// =============================================================================

export async function getFeedbackList(
  status?: SubmissionStatus,
  page?: number
): Promise<PaginatedResponse<PlayerFeedback>> {
  const params = new URLSearchParams();
  if (status) {
    params.append('status', status);
  }
  if (page) {
    params.append('page', page.toString());
  }
  const qs = params.toString();
  const res = await apiFetch(`${SUBMISSIONS_URL}/feedback/${qs ? `?${qs}` : ''}`);
  if (!res.ok) throw new Error('Failed to load feedback list');
  return res.json();
}

export async function getFeedbackDetail(id: number): Promise<PlayerFeedback> {
  const res = await apiFetch(`${SUBMISSIONS_URL}/feedback/${id}/`);
  if (!res.ok) throw new Error('Failed to load feedback detail');
  return res.json();
}

export async function updateFeedbackStatus(
  id: number,
  status: SubmissionStatus
): Promise<PlayerFeedback> {
  const res = await apiFetch(`${SUBMISSIONS_URL}/feedback/${id}/`, {
    method: 'PATCH',
    body: JSON.stringify({ status }),
  });
  if (!res.ok) throw new Error('Failed to update feedback status');
  return res.json();
}

// =============================================================================
// Bug Reports
// =============================================================================

export async function getBugReportList(
  status?: SubmissionStatus,
  page?: number
): Promise<PaginatedResponse<BugReport>> {
  const params = new URLSearchParams();
  if (status) {
    params.append('status', status);
  }
  if (page) {
    params.append('page', page.toString());
  }
  const qs = params.toString();
  const res = await apiFetch(`${SUBMISSIONS_URL}/bug-reports/${qs ? `?${qs}` : ''}`);
  if (!res.ok) throw new Error('Failed to load bug report list');
  return res.json();
}

export async function getBugReportDetail(id: number): Promise<BugReport> {
  const res = await apiFetch(`${SUBMISSIONS_URL}/bug-reports/${id}/`);
  if (!res.ok) throw new Error('Failed to load bug report detail');
  return res.json();
}

export async function updateBugReportStatus(
  id: number,
  status: SubmissionStatus
): Promise<BugReport> {
  const res = await apiFetch(`${SUBMISSIONS_URL}/bug-reports/${id}/`, {
    method: 'PATCH',
    body: JSON.stringify({ status }),
  });
  if (!res.ok) throw new Error('Failed to update bug report status');
  return res.json();
}

// =============================================================================
// Player Reports
// =============================================================================

export async function getPlayerReportList(
  status?: SubmissionStatus,
  page?: number
): Promise<PaginatedResponse<PlayerReport>> {
  const params = new URLSearchParams();
  if (status) {
    params.append('status', status);
  }
  if (page) {
    params.append('page', page.toString());
  }
  const qs = params.toString();
  const res = await apiFetch(`${SUBMISSIONS_URL}/player-reports/${qs ? `?${qs}` : ''}`);
  if (!res.ok) throw new Error('Failed to load player report list');
  return res.json();
}

export async function getPlayerReportDetail(id: number): Promise<PlayerReport> {
  const res = await apiFetch(`${SUBMISSIONS_URL}/player-reports/${id}/`);
  if (!res.ok) throw new Error('Failed to load player report detail');
  return res.json();
}

export async function updatePlayerReportStatus(
  id: number,
  status: SubmissionStatus
): Promise<PlayerReport> {
  const res = await apiFetch(`${SUBMISSIONS_URL}/player-reports/${id}/`, {
    method: 'PATCH',
    body: JSON.stringify({ status }),
  });
  if (!res.ok) throw new Error('Failed to update player report status');
  return res.json();
}

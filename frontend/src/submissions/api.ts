/**
 * Player submission API — feedback and bug reports.
 *
 * Player reports (reporting problematic behavior from another player) are
 * intentionally NOT exposed here. That flow requires a dedicated safety-
 * focused design pass (wording, block/mute integration, evidence handling)
 * and lives in the roadmap under Phase 5b-followup.
 */

import { apiFetch } from '@/evennia_replacements/api';

export interface SubmitFeedbackRequest {
  reporter_persona: number;
  description: string;
}

export interface SubmitBugReportRequest {
  reporter_persona: number;
  description: string;
}

export async function submitFeedback(data: SubmitFeedbackRequest): Promise<{ id: number }> {
  const res = await apiFetch('/api/player-submissions/feedback/', {
    method: 'POST',
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(detail || 'Failed to submit feedback.');
  }
  return res.json();
}

export async function submitBugReport(data: SubmitBugReportRequest): Promise<{ id: number }> {
  const res = await apiFetch('/api/player-submissions/bug-reports/', {
    method: 'POST',
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(detail || 'Failed to submit bug report.');
  }
  return res.json();
}

/** Emergency-only structured petition (#2288). */
export interface PetitionRow {
  id: number;
  category: string;
  category_display: string;
  scene: number | null;
  subject_character: number | null;
  description: string;
  status: string;
  staff_notes: string;
  created_at: string;
  resolved_at: string | null;
}

export interface SubmitPetitionRequest {
  category: string;
  description: string;
  scene?: number | null;
  subject_character?: number | null;
}

export async function submitPetition(data: SubmitPetitionRequest): Promise<PetitionRow> {
  const res = await apiFetch('/api/player-submissions/petitions/', {
    method: 'POST',
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    let detail = '';
    try {
      detail = ((await res.json()) as { detail?: string }).detail ?? '';
    } catch {
      detail = '';
    }
    throw new Error(detail || 'Failed to submit the petition.');
  }
  return res.json();
}

export async function fetchMyPetitions(): Promise<PetitionRow[]> {
  const res = await apiFetch('/api/player-submissions/petitions/');
  if (!res.ok) throw new Error('Failed to load your petitions.');
  const data = (await res.json()) as { results: PetitionRow[] } | PetitionRow[];
  return Array.isArray(data) ? data : data.results;
}

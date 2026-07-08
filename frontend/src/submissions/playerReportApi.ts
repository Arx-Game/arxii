/**
 * Player report API — reporting problematic behavior from another player (#1279).
 *
 * Unlike feedback/bug-reports, a player report needs a reported persona, a category,
 * and the "what you already did" fields (asked_to_stop, blocked_or_muted).
 */

import { apiFetch } from '@/evennia_replacements/api';

export interface PlayerReportCreateRequest {
  reporter_persona: number;
  reported_persona_name: string;
  category: string;
  behavior_description: string;
  asked_to_stop: boolean;
  blocked_or_muted: boolean;
  scene?: number;
  interaction?: number;
}

export interface PlayerReportCreateResponse {
  id: number;
}

export async function createPlayerReport(
  data: PlayerReportCreateRequest
): Promise<PlayerReportCreateResponse> {
  const res = await apiFetch('/api/player-submissions/player-reports/', {
    method: 'POST',
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(detail || 'Failed to submit report.');
  }
  return res.json();
}

/** Character Secrets REST calls (#1334, #1429). */
import { apiFetch } from '@/evennia_replacements/api';

import type { GrievanceOption, PaginatedKnownSecretList } from './types';

/** Secrets the active viewing character (`viewerId`, a RosterEntry pk) knows about `subjectId`. */
export async function listKnownSecrets(
  subjectId: number,
  viewerId: number
): Promise<PaginatedKnownSecretList> {
  const res = await apiFetch(`/api/secrets/known/?subject=${subjectId}&viewer=${viewerId}`);
  if (!res.ok) {
    throw new Error('Failed to load secrets');
  }
  return res.json() as Promise<PaginatedKnownSecretList>;
}

/** The preset grievance responses a wronged character may choose from (#1429). */
export async function listGrievanceOptions(): Promise<GrievanceOption[]> {
  const res = await apiFetch('/api/secrets/grievance-options/');
  if (!res.ok) {
    throw new Error('Failed to load grievance options');
  }
  return res.json() as Promise<GrievanceOption[]>;
}

export interface SubmitGrievancePayload {
  secret: number;
  viewer: number;
  option?: number;
  customPoints?: number;
  customTrack?: number;
}

/** Register the active character's grievance against a secret's subject (#1429). */
export async function submitGrievance(payload: SubmitGrievancePayload): Promise<void> {
  const res = await apiFetch('/api/secrets/grievance/', {
    method: 'POST',
    body: JSON.stringify({
      secret: payload.secret,
      viewer: payload.viewer,
      option: payload.option ?? null,
      custom_points: payload.customPoints ?? null,
      custom_track: payload.customTrack ?? null,
    }),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new Error(detail?.detail ?? 'Failed to register grievance');
  }
}

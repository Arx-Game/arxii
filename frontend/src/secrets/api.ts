/** Character Secrets REST calls (#1334, #1429, #3266). */
import { apiFetch } from '@/evennia_replacements/api';

import type {
  AuthoredSecret,
  GossipResult,
  GossipSecret,
  GrievanceOption,
  PaginatedAuthoredSecretList,
  PaginatedKnownSecretList,
  SecretCategoryOption,
} from './types';

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

/** The Level-1 secrets the active character could spread, with heat in their current region (#1572). */
export async function listGossip(viewerId: number): Promise<GossipSecret[]> {
  const res = await apiFetch(`/api/secrets/gossip/?viewer=${viewerId}`);
  if (!res.ok) {
    throw new Error('Failed to load gossip');
  }
  return res.json() as Promise<GossipSecret[]>;
}

export interface GossipActionPayload {
  action: 'plant' | 'seek' | 'suppress';
  viewer: number;
  secret?: number;
}

/** Plant / seek / suppress gossip at a social hub (#1572) — the web face of the `gossip` command. */
export async function gossipAction(payload: GossipActionPayload): Promise<GossipResult> {
  const res = await apiFetch('/api/secrets/gossip/action/', {
    method: 'POST',
    body: JSON.stringify({
      action: payload.action,
      viewer: payload.viewer,
      secret: payload.secret ?? null,
    }),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new Error(detail?.detail ?? 'Gossip failed');
  }
  return res.json() as Promise<GossipResult>;
}

/** Staff-only omniscient view of a character's authored secrets (#3266). */
export async function getAuthoredSecrets(subjectId: number): Promise<PaginatedAuthoredSecretList> {
  const res = await apiFetch(`/api/secrets/authored/?subject=${subjectId}`);
  if (!res.ok) {
    throw new Error('Failed to load authored secrets');
  }
  return res.json() as Promise<PaginatedAuthoredSecretList>;
}

/** The staff-authored category catalog a secret's category select is fed by (#3266). */
export async function getSecretCategories(): Promise<SecretCategoryOption[]> {
  const res = await apiFetch('/api/secrets/authored/categories/');
  if (!res.ok) {
    throw new Error('Failed to load secret categories');
  }
  return res.json() as Promise<SecretCategoryOption[]>;
}

export interface AuthorSecretPayload {
  subject_sheet: number;
  content: string;
  level?: number;
  category?: number | null;
  consequences?: string;
  subject_aware?: boolean;
}

/** Staff-mint a new secret about a character (#3266). Provenance is fixed server-side. */
export async function createAuthoredSecret(payload: AuthorSecretPayload): Promise<AuthoredSecret> {
  const res = await apiFetch('/api/secrets/authored/', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new Error(detail?.detail ?? 'Failed to author secret');
  }
  return res.json() as Promise<AuthoredSecret>;
}

export type UpdateAuthoredSecretPayload = Partial<Omit<AuthorSecretPayload, 'subject_sheet'>>;

/** Staff-edit an authored secret's editable fields (#3266). Subject is immutable after mint. */
export async function updateAuthoredSecret(
  id: number,
  payload: UpdateAuthoredSecretPayload
): Promise<AuthoredSecret> {
  const res = await apiFetch(`/api/secrets/authored/${id}/`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new Error(detail?.detail ?? 'Failed to update secret');
  }
  return res.json() as Promise<AuthoredSecret>;
}

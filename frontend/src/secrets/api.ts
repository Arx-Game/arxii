/** Character Secrets REST calls (#1334, #1429). */
import { apiFetch } from '@/evennia_replacements/api';

import type {
  GossipResult,
  GossipSecret,
  GrievanceOption,
  PaginatedKnownSecretList,
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

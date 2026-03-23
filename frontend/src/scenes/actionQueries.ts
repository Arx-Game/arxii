import { apiFetch } from '@/evennia_replacements/api';
import type {
  AvailableActionsResponse,
  ActionRequest,
  ActionRequestResponse,
  Place,
} from './actionTypes';

export async function fetchAvailableActions(sceneId: string): Promise<AvailableActionsResponse> {
  const res = await apiFetch(`/api/scenes/${sceneId}/actions/available/`);
  if (!res.ok) throw new Error('Failed to load available actions');
  return res.json();
}

export async function createActionRequest(
  sceneId: string,
  body: {
    action_key: string;
    target_persona_id?: number;
    technique_id?: number;
  }
): Promise<ActionRequestResponse> {
  const res = await apiFetch(`/api/scenes/${sceneId}/actions/perform/`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error('Failed to perform action');
  return res.json();
}

export async function fetchPendingRequests(sceneId: string): Promise<{ results: ActionRequest[] }> {
  const res = await apiFetch(`/api/scenes/${sceneId}/actions/requests/`);
  if (!res.ok) throw new Error('Failed to load pending requests');
  return res.json();
}

export async function respondToRequest(
  sceneId: string,
  requestId: number,
  body: { accept: boolean; difficulty?: string }
): Promise<ActionRequestResponse> {
  const res = await apiFetch(`/api/scenes/${sceneId}/actions/requests/${requestId}/respond/`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error('Failed to respond to action request');
  return res.json();
}

export async function fetchPlaces(sceneId: string): Promise<{ results: Place[] }> {
  const res = await apiFetch(`/api/scenes/${sceneId}/places/`);
  if (!res.ok) throw new Error('Failed to load places');
  return res.json();
}

export async function joinPlace(sceneId: string, placeId: number): Promise<void> {
  const res = await apiFetch(`/api/scenes/${sceneId}/places/${placeId}/join/`, { method: 'POST' });
  if (!res.ok) throw new Error('Failed to join place');
}

export async function leavePlace(sceneId: string, placeId: number): Promise<void> {
  const res = await apiFetch(`/api/scenes/${sceneId}/places/${placeId}/leave/`, { method: 'POST' });
  if (!res.ok) throw new Error('Failed to leave place');
}

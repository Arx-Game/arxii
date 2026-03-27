import { apiFetch } from '@/evennia_replacements/api';
import type {
  AvailableActionsResponse,
  ActionRequest,
  ActionRequestResponse,
  Place,
} from './actionTypes';

// NOTE: There is no backend endpoint for "available actions" yet.
// This function is a placeholder that returns empty results until the
// backend implements an available-actions discovery endpoint.
// The ActionPanel and ActionAttachment components depend on this shape.
export async function fetchAvailableActions(_sceneId: string): Promise<AvailableActionsResponse> {
  // TODO: Implement when backend adds GET /api/action-requests/available/?scene=X
  return { self_actions: [], targeted_actions: [], technique_actions: [] };
}

export async function createActionRequest(
  sceneId: string,
  body: {
    action_key: string;
    target_persona_id?: number;
    technique_id?: number;
  }
): Promise<ActionRequestResponse> {
  // Backend SceneActionRequestCreateSerializer expects:
  //   scene (int), target_persona (int), action_key (str), difficulty_choice? (str)
  const requestBody: Record<string, unknown> = {
    scene: Number(sceneId),
    action_key: body.action_key,
  };
  if (body.target_persona_id !== undefined) {
    requestBody.target_persona = body.target_persona_id;
  }
  const res = await apiFetch('/api/action-requests/', {
    method: 'POST',
    body: JSON.stringify(requestBody),
  });
  if (!res.ok) throw new Error('Failed to perform action');
  return res.json();
}

export async function fetchPendingRequests(sceneId: string): Promise<{ results: ActionRequest[] }> {
  const res = await apiFetch(`/api/action-requests/?scene=${sceneId}&status=pending`);
  if (!res.ok) throw new Error('Failed to load pending requests');
  return res.json();
}

export async function respondToRequest(
  _sceneId: string,
  requestId: number,
  body: { accept: boolean; difficulty?: string }
): Promise<ActionRequestResponse> {
  // Backend ConsentResponseSerializer expects: { decision: "accept" | "deny" }
  // Map the frontend { accept, difficulty } shape to the backend shape.
  const decision = body.accept ? 'accept' : 'deny';
  const res = await apiFetch(`/api/action-requests/${requestId}/respond/`, {
    method: 'POST',
    body: JSON.stringify({ decision }),
  });
  if (!res.ok) throw new Error('Failed to respond to action request');
  return res.json();
}

export async function fetchPlaces(sceneId: string): Promise<{ results: Place[] }> {
  // PlaceFilter supports ?room=X for filtering by room
  const res = await apiFetch(`/api/places/?room=${sceneId}`);
  if (!res.ok) throw new Error('Failed to load places');
  return res.json();
}

export async function joinPlace(_sceneId: string, placeId: number): Promise<void> {
  const res = await apiFetch(`/api/places/${placeId}/join/`, { method: 'POST' });
  if (!res.ok) throw new Error('Failed to join place');
}

export async function leavePlace(_sceneId: string, placeId: number): Promise<void> {
  const res = await apiFetch(`/api/places/${placeId}/leave/`, { method: 'POST' });
  if (!res.ok) throw new Error('Failed to leave place');
}

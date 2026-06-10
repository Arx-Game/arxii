import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '@/evennia_replacements/api';
import type {
  PlayerActionsResponse,
  ActionRequest,
  ActionRequestResponse,
  Place,
  CastableTechnique,
  CastPullRequestBody,
  CastRequestBody,
  CastResponse,
} from './actionTypes';

/**
 * Fetch unified available actions for a character.
 *
 * Calls GET /api/actions/characters/<characterId>/available/ — the unified
 * challenge + combat + registry availability endpoint introduced in the
 * unified-action-interface initiative.  Returns a paginated PlayerAction list.
 *
 * Each PlayerAction carries inline `target_spec`, `enhancements`, and `strain`
 * fields — the old `/api/action-requests/available/` endpoint and its
 * `fetchSceneActions` helper have been removed in favor of this unified shape.
 */
export async function fetchAvailableActions(characterId: number): Promise<PlayerActionsResponse> {
  const res = await apiFetch(`/api/actions/characters/${characterId}/available/`);
  if (!res.ok) throw new Error('Failed to load available actions');
  return res.json() as Promise<PlayerActionsResponse>;
}

export async function createActionRequest(
  sceneId: string,
  body: {
    action_key: string;
    target_persona_id?: number;
    technique_id?: number;
    initiator_persona?: number;
    strain_commitment?: number;
  }
): Promise<ActionRequestResponse> {
  // Backend SceneActionRequestCreateSerializer expects:
  //   scene (int), target_persona (int), action_key (str), technique_id? (int),
  //   strain_commitment? (int, validated against anima at resolution time).
  const requestBody: Record<string, unknown> = {
    scene: Number(sceneId),
    action_key: body.action_key,
  };
  if (body.target_persona_id !== undefined) {
    requestBody.target_persona = body.target_persona_id;
  }
  if (body.technique_id !== undefined) {
    requestBody.technique_id = body.technique_id;
  }
  if (body.initiator_persona !== undefined) {
    requestBody.initiator_persona = body.initiator_persona;
  }
  if (body.strain_commitment !== undefined) {
    requestBody.strain_commitment = body.strain_commitment;
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

/**
 * POST /api/action-requests/cast/ — submit a standalone technique cast.
 *
 * Routes per the consent/combat/immediate matrix:
 *   - self/room/no-target → resolves immediately (result in response)
 *   - benign at another PC → PENDING consent request (no result yet)
 *   - hostile at another PC → seeds/feeds a combat encounter
 */
export async function castTechnique(
  sceneId: string,
  params: {
    initiator_persona: number;
    technique_id: number;
    target_persona?: number | null;
    strain_commitment?: number;
    pull?: CastPullRequestBody;
  }
): Promise<CastResponse> {
  const body: CastRequestBody = {
    scene: Number(sceneId),
    initiator_persona: params.initiator_persona,
    technique_id: params.technique_id,
  };
  if (params.target_persona !== undefined) {
    body.target_persona = params.target_persona;
  }
  if (params.strain_commitment !== undefined) {
    body.strain_commitment = params.strain_commitment;
  }
  if (params.pull !== undefined) {
    body.pull = params.pull;
  }
  const res = await apiFetch('/api/action-requests/cast/', {
    method: 'POST',
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error('Failed to cast technique');
  return res.json();
}

/**
 * Fetch castable techniques for a given initiator persona.
 *
 * Calls GET /api/action-requests/castable-techniques/?initiator_persona=<id>
 * Returns only techniques with an action_template (castable standalone)
 * known by that character.
 */
export async function fetchCastableTechniques(
  initiatorPersonaId: number
): Promise<CastableTechnique[]> {
  const res = await apiFetch(
    `/api/action-requests/castable-techniques/?initiator_persona=${initiatorPersonaId}`
  );
  if (!res.ok) throw new Error('Failed to load castable techniques');
  return res.json() as Promise<CastableTechnique[]>;
}

/**
 * TanStack Query hook for castable techniques.
 * Mirrors the pattern used by fetchAvailableActions.
 */
export function useCastableTechniques(initiatorPersonaId: number | null) {
  return useQuery({
    queryKey: ['castable-techniques', initiatorPersonaId],
    queryFn: () => fetchCastableTechniques(initiatorPersonaId!),
    enabled: initiatorPersonaId !== null,
  });
}

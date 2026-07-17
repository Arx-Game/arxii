import { useMutation, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from '@/evennia_replacements/api';
import { throwApiError } from '@/lib/errors';
import type { HighlightReel, Interaction, ReactionEmojiEntry, SceneRoundModeValue } from './types';

// ---------------------------------------------------------------------------
// Query key factory
// ---------------------------------------------------------------------------

/**
 * Query key factory for scene queries.
 *
 * detail(id) produces ['scene', String(id)], which matches the legacy raw-array
 * shape used in SceneDetailPage (`queryKey: ['scene', id]`). This factory was
 * introduced so the now-deleted CombatScenePage (#2197 folded its rail into
 * SceneDetailPage) shared the same cache entry as SceneDetailPage's own scene
 * query and avoided a double fetch. SceneDetailPage still uses the legacy
 * shape directly; refactor it to use this factory in a separate PR.
 */
export const sceneKeys = {
  all: ['scene'] as const,
  detail: (id: string | number) => ['scene', String(id)] as const,
};

export type {
  RosterEntryRef,
  SceneParticipant,
  SceneLocation,
  SceneListItem,
  SceneDetail,
  Interaction,
  HighlightReel,
  SceneRoundModeValue,
} from './types';

export async function fetchScenes(params: string) {
  const res = await apiFetch(`/api/scenes/?${params}`);
  if (!res.ok) throw new Error('Failed to load scenes');
  return res.json();
}

export async function fetchScene(id: string) {
  const res = await apiFetch(`/api/scenes/${id}/`);
  if (!res.ok) throw new Error('Failed to load scene');
  return res.json();
}

export async function startScene(location: number, name?: string) {
  const res = await apiFetch('/api/scenes/', {
    method: 'POST',
    body: JSON.stringify({ location_id: location, name }),
  });
  if (!res.ok) throw new Error('Failed to start scene');
  return res.json();
}

export async function updateScene(id: string, data: { name?: string; description?: string }) {
  const res = await apiFetch(`/api/scenes/${id}/`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error('Failed to update scene');
  return res.json();
}

export async function finishScene(id: string) {
  const res = await apiFetch(`/api/scenes/${id}/finish/`, { method: 'POST' });
  if (!res.ok) throw new Error('Failed to finish scene');
  return res.json();
}

export interface SetRoundModePayload {
  mode?: SceneRoundModeValue;
  advance_quorum_pct?: number;
  max_actions_per_round?: number;
  per_target_repeat_lock?: boolean;
}

export async function setRoundMode(id: string, payload: SetRoundModePayload) {
  const res = await apiFetch(`/api/scenes/${id}/set-round-mode/`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
  if (!res.ok) await throwApiError(res, 'Failed to set round mode');
  return res.json();
}

export async function fetchInteractions(sceneId: string, cursor?: string) {
  const url = new URL('/api/interactions/', window.location.origin);
  url.searchParams.set('scene', sceneId);
  if (cursor) url.searchParams.set('cursor', cursor);
  const res = await apiFetch(url.pathname + url.search);
  if (!res.ok) throw new Error('Failed to load interactions');
  return res.json();
}

/** Fetch a single interaction's full detail — used to reveal a sealed reel moment (#1241). */
export async function fetchInteraction(interactionId: number): Promise<Interaction> {
  const res = await apiFetch(`/api/interactions/${interactionId}/`);
  if (!res.ok) throw new Error('Failed to load interaction');
  return res.json();
}

/** Fetch a scene's highlight reel: a sealed featured moment + a ranked index (#1241). */
export async function fetchHighlightReel(sceneId: string): Promise<HighlightReel> {
  const res = await apiFetch(`/api/scenes/${sceneId}/highlight-reel/`);
  if (!res.ok) throw new Error('Failed to load highlight reel');
  return res.json();
}

export interface InteractionReactionResponse {
  bump_applied: boolean;
  bump_message: string | null;
}

export async function postInteractionReaction(
  interactionId: number,
  emoji: string
): Promise<InteractionReactionResponse | null> {
  const res = await apiFetch('/api/interaction-reactions/', {
    method: 'POST',
    body: JSON.stringify({ interaction: interactionId, emoji }),
  });
  // Toggle returns 201 (created) or 204 (removed) — both are success
  if (!res.ok && res.status !== 204) throw new Error('Failed to toggle reaction');
  return res.status === 204 ? null : res.json();
}

/** Fetch the active reaction-emoji catalog (#1699); valenced entries also nudge regard. */
export async function fetchReactionEmojiCatalog(): Promise<ReactionEmojiEntry[]> {
  const res = await apiFetch('/api/reaction-emoji/');
  if (!res.ok) throw new Error('Failed to load reaction emoji catalog');
  const data = (await res.json()) as { results: ReactionEmojiEntry[] };
  return data.results;
}

export interface PendingUnlinkedActionRow {
  id: number;
  content: string;
  mode: string;
  timestamp: string;
}

export async function fetchPendingUnlinkedActions(
  sceneId: string,
  personaId: number
): Promise<PendingUnlinkedActionRow[]> {
  const url = new URL('/api/interactions/', window.location.origin);
  url.searchParams.set('scene', sceneId);
  url.searchParams.set('persona', String(personaId));
  url.searchParams.set('mode', 'action');
  url.searchParams.set('without_pose_link', 'true');
  const res = await apiFetch(url.pathname + url.search);
  if (!res.ok) throw new Error('Failed to load pending unlinked actions');
  const data = (await res.json()) as { results: PendingUnlinkedActionRow[] };
  return data.results;
}

export interface SubmitPoseBody {
  persona_id: number;
  scene_id?: number;
  content: string;
  /** When provided (including empty array), overrides auto-link. Omit to auto-link. */
  action_link_ids?: number[];
  /** PoseKind: 'entry' opens a Make-an-Entrance reaction window (#904). */
  pose_kind?: string;
  /**
   * Composer-mode @Name targets (#2156) — resolved server-side with the same
   * semantics as the WS `@Name`-prefix parser (unresolvable names are silently
   * skipped, not an error).
   */
  target_names?: string[];
}

/**
 * The submit-pose response body (`InteractionListSerializer` output), or
 * `{ ephemeral: true }` for ephemeral scenes that never persist an Interaction
 * row (#2156). `id` is what callers need to link a follow-up action request
 * (e.g. the technique-driven entrance's `entry_interaction_id`, #2183).
 */
export interface SubmitPoseResult {
  id?: number;
  ephemeral?: boolean;
}

export async function submitPose(body: SubmitPoseBody): Promise<SubmitPoseResult> {
  const res = await apiFetch('/api/interactions/submit-pose/', {
    method: 'POST',
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const data = (await res.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(data?.detail || 'Failed to submit pose');
  }
  return res.json();
}

// ---------------------------------------------------------------------------
// Dramatic-moment types + tags (#1139)
// ---------------------------------------------------------------------------

export interface DramaticMomentType {
  id: number;
  label: string;
  description?: string;
  resonance: number;
  resonance_amount?: number;
  per_scene_cap?: number;
}

export async function fetchDramaticMomentTypes(): Promise<DramaticMomentType[]> {
  const res = await apiFetch('/api/magic/dramatic-moment-types/');
  if (!res.ok) throw new Error('Failed to load dramatic moment types');
  return res.json();
}

export async function postDramaticMomentTag(body: {
  moment_type: number;
  interaction?: number;
  character_sheet?: number;
  scene?: number;
}): Promise<void> {
  const res = await apiFetch('/api/magic/dramatic-moment-tags/', {
    method: 'POST',
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error('Failed to tag dramatic moment');
}

// ---------------------------------------------------------------------------
// Dramatic-moment GM suggestion inbox — confirm/dismiss (#2183)
// ---------------------------------------------------------------------------

export async function confirmDramaticMomentSuggestion(suggestionId: number): Promise<void> {
  const res = await apiFetch(`/api/magic/dramatic-moment-suggestions/${suggestionId}/confirm/`, {
    method: 'POST',
  });
  if (!res.ok) {
    const data = (await res.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(data?.detail || 'Failed to confirm dramatic moment');
  }
}

export async function dismissDramaticMomentSuggestion(suggestionId: number): Promise<void> {
  const res = await apiFetch(`/api/magic/dramatic-moment-suggestions/${suggestionId}/dismiss/`, {
    method: 'POST',
  });
  if (!res.ok) {
    const data = (await res.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(data?.detail || 'Failed to dismiss dramatic moment');
  }
}

export function useConfirmDramaticMomentSuggestion(sceneId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: confirmDramaticMomentSuggestion,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['scene-interactions', sceneId] }),
  });
}

export function useDismissDramaticMomentSuggestion(sceneId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: dismissDramaticMomentSuggestion,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['scene-interactions', sceneId] }),
  });
}

export async function reactToWindow(
  windowId: number,
  body: { persona_id: number; choice: string }
): Promise<void> {
  const res = await apiFetch(`/api/reaction-windows/${windowId}/react/`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const data = (await res.json().catch(() => null)) as { detail?: string[] | string } | null;
    const detail = Array.isArray(data?.detail) ? data.detail[0] : data?.detail;
    throw new Error(detail || 'Failed to react');
  }
}

export async function reactToInteraction(body: {
  persona_id: number;
  interaction_id: number;
  kind: string;
  choice: string;
}): Promise<void> {
  const res = await apiFetch('/api/reaction-windows/react-to-interaction/', {
    method: 'POST',
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const data = (await res.json().catch(() => null)) as { detail?: string[] | string } | null;
    const detail = Array.isArray(data?.detail) ? data.detail[0] : data?.detail;
    throw new Error(detail || 'Failed to react');
  }
}

export async function createPoseEndorsement(body: { interaction: number; resonance: number }) {
  const res = await apiFetch('/api/magic/pose-endorsements/', {
    method: 'POST',
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error('Failed to endorse pose');
  return res.json();
}

export async function deletePoseEndorsement(id: number) {
  const res = await apiFetch(`/api/magic/pose-endorsements/${id}/`, { method: 'DELETE' });
  if (!res.ok) throw new Error('Failed to retract endorsement');
}

export async function createSceneEntryEndorsement(body: {
  endorsee_sheet: number;
  scene: number;
  resonance: number;
}) {
  const res = await apiFetch('/api/magic/scene-entry-endorsements/', {
    method: 'POST',
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error('Failed to endorse entry');
  return res.json();
}

export function useCreatePoseEndorsement(sceneId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createPoseEndorsement,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['scene-interactions', sceneId] }),
  });
}

export function useDeletePoseEndorsement(sceneId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: deletePoseEndorsement,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['scene-interactions', sceneId] }),
  });
}

export function useCreateSceneEntryEndorsement(sceneId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createSceneEntryEndorsement,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['scene-interactions', sceneId] }),
  });
}

/**
 * Style-presentation endorsement (#2031). Mirrors createSceneEntryEndorsement's
 * shape — endorser is resolved server-side; immutable (no retract). Backend
 * error messages are meaningful ("not wearing a bound style", etc.) and must
 * surface verbatim, so the `detail` string is extracted like setRoundMode's idiom.
 */
export async function createStyleEndorsement(body: {
  endorsee_sheet: number;
  scene: number;
  resonance: number;
}) {
  const res = await apiFetch('/api/magic/style-presentation-endorsements/', {
    method: 'POST',
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const data = (await res.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(data?.detail || 'Failed to endorse style');
  }
  return res.json();
}

export function useCreateStyleEndorsement(sceneId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createStyleEndorsement,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['scene-interactions', sceneId] }),
  });
}

export function useSetRoundMode(sceneId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: SetRoundModePayload) => setRoundMode(sceneId, payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['scene', sceneId] }),
  });
}

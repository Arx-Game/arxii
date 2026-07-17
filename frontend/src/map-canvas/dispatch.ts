/**
 * Shared REGISTRY-dispatch POST/parse/success-shape logic behind
 * `dispatchRoomBuilder` (`@/buildings/api`, #670) and `dispatchWorldBuilder`
 * (`@/world-builder/api`, #2449) — both dispatch
 * `POST /api/actions/characters/<id>/dispatch/` with a `registry` backend
 * ref and parse the same `DispatchResultSerializer` response shape. Each
 * caller wraps this with its own registry-key union so callers keep
 * compile-time key checking per app (Sonar dedup fix pass, #2449).
 */
import { apiFetch } from '@/evennia_replacements/api';
import { throwApiError } from '@/lib/errors';

/**
 * Result of a REGISTRY dispatch. `success` mirrors `DispatchResultSerializer`
 * (`src/actions/serializers.py:270-275`): the view always returns HTTP 200 for
 * a business-rule refusal, so `success === false` is the wire signal callers
 * must check to distinguish an honest failure from a real success — `null`
 * means the backend detail wasn't an `ActionResult` (not expected for the
 * REGISTRY-backed builder actions this dispatches, but treated as success so
 * a null never silently swallows a real failure toast).
 */
export interface DispatchResult {
  message: string;
  success: boolean | null;
}

/**
 * Dispatch a REGISTRY action for `characterId`. Returns the action's
 * human-readable result message plus its `success` flag; throws with the
 * server `detail` on 4xx. `registryKey` is typed `string` here — callers pin
 * their own key union in a thin wrapper (see `dispatchRoomBuilder`,
 * `dispatchWorldBuilder`).
 */
export async function dispatchCanvasAction(
  characterId: number,
  registryKey: string,
  kwargs: Record<string, unknown>
): Promise<DispatchResult> {
  const res = await apiFetch(`/api/actions/characters/${characterId}/dispatch/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ref: { backend: 'registry', registry_key: registryKey }, kwargs }),
  });
  if (!res.ok) await throwApiError(res, 'The action failed.');
  const data = (await res.json()) as { message?: string | null; success?: boolean | null };
  return { message: data.message ?? 'Done.', success: data.success ?? null };
}

/**
 * Magic API functions
 *
 * Covers Soul Tether endpoints, Thread reads, CharacterResonance reads,
 * Thread Hub Summary, Thread mutations (weave/patch/retire/imbue/cross-xp-lock),
 * pull preview/commit, teaching offers, and rooms-by-property.
 *
 * Uses apiFetch from @/evennia_replacements/api.
 *
 * Note: Soul Tether *formation* (acceptance) goes through
 * POST /api/magic/rituals/perform/ via usePerformRitual in the rituals module.
 */

import { apiFetch } from '@/evennia_replacements/api';
import { getRituals } from '@/rituals/api';
import type { components } from '@/generated/api';
import type {
  AcceptTeachingOfferRequest,
  AcceptTeachingOfferResponse,
  ApplicablePullsRequest,
  CharacterResonance,
  CrossXPLockRequest,
  CrossXPLockResponse,
  DissolveRequest,
  ImbueRequest,
  ImbueResponse,
  PaginatedPendingStageAdvanceOfferList,
  PaginatedSineatingPendingOfferList,
  PaginatedTeachingOfferList,
  PaginatedThreadList,
  PatchThreadRequest,
  PendingStageAdvanceOffer,
  PullCommitRequest,
  PullCommitResponse,
  PullPreviewRequest,
  PullPreviewResponse,
  RescueOutcome,
  RescueRequest,
  RoomBrief,
  SineatingOffer,
  SineatingPendingOffer,
  SineatingRequest,
  SineatingRespondRequest,
  SineatingResult,
  SoulTetherDetail,
  StageAdvanceBonusResult,
  StageAdvanceRespondRequest,
  TetherBond,
  Thread,
  ThreadApplicability,
  ThreadHubSummary,
  WeaveThreadRequest,
} from './types';

export type Technique = components['schemas']['Technique'];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function jsonHeaders(): HeadersInit {
  return { 'Content-Type': 'application/json' };
}

async function parseErrorDetail(res: Response, fallback: string): Promise<never> {
  let detail = fallback;
  try {
    const data = (await res.json()) as { detail?: string };
    if (typeof data.detail === 'string' && data.detail.trim()) {
      detail = data.detail;
    }
  } catch {
    // body wasn't JSON; keep generic
  }
  throw new Error(detail);
}

// ---------------------------------------------------------------------------
// URL constants
// ---------------------------------------------------------------------------

const SOUL_TETHER_URL = '/api/magic/soul-tether';
const THREADS_URL = '/api/magic/threads';
const CHAR_RESONANCES_URL = '/api/magic/character-resonances';
const RELATIONSHIPS_URL = '/api/relationships/relationships';
const THREAD_HUB_SUMMARY_URL = '/api/magic/thread-hub-summary/';
const THREAD_PULL_PREVIEW_URL = '/api/magic/thread-pull-preview/';
const THREAD_PULL_COMMIT_URL = '/api/magic/thread-pull-commit/';
const TEACHING_OFFERS_URL = '/api/magic/teaching-offers';
const ROOMS_BY_PROPERTY_URL = '/api/magic/rooms-by-property/';
const TECHNIQUES_URL = '/api/magic/techniques';

// ---------------------------------------------------------------------------
// Soul Tether reads
// ---------------------------------------------------------------------------

/**
 * GET /api/magic/soul-tether/{relationship_id}/
 *
 * Returns tether state: Hollow current/max, Thread levels, Sineater stats.
 * The path param is the CharacterRelationship PK — either directional row works.
 */
export async function getSoulTetherDetail(relationshipId: number): Promise<SoulTetherDetail> {
  const res = await apiFetch(`${SOUL_TETHER_URL}/${relationshipId}/`);
  if (!res.ok)
    throw new Error(`Failed to load soul-tether detail for relationship ${relationshipId}`);
  return res.json() as Promise<SoulTetherDetail>;
}

/**
 * GET /api/magic/soul-tether/sineating/pending/
 *
 * Sineater-facing inbox: pending Sineating offers addressed to the caller.
 */
export async function getPendingSineatingOffers(): Promise<PaginatedSineatingPendingOfferList> {
  const res = await apiFetch(`${SOUL_TETHER_URL}/sineating/pending/`);
  if (!res.ok) throw new Error('Failed to load pending Sineating offers');
  return res.json() as Promise<PaginatedSineatingPendingOfferList>;
}

/**
 * GET /api/magic/soul-tether/stage-advance/pending/
 *
 * Sineater-facing inbox: pending stage-advance bonus offers.
 */
export async function getPendingStageAdvanceOffers(): Promise<PaginatedPendingStageAdvanceOfferList> {
  const res = await apiFetch(`${SOUL_TETHER_URL}/stage-advance/pending/`);
  if (!res.ok) throw new Error('Failed to load pending stage-advance offers');
  return res.json() as Promise<PaginatedPendingStageAdvanceOfferList>;
}

// ---------------------------------------------------------------------------
// Soul Tether mutations
// ---------------------------------------------------------------------------

/**
 * POST /api/magic/soul-tether/dissolve/
 *
 * Either party may dissolve the bond. Returns 200 with no body on success.
 */
export async function dissolveSoulTether(body: DissolveRequest): Promise<void> {
  const res = await apiFetch(`${SOUL_TETHER_URL}/dissolve/`, {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    await parseErrorDetail(res, 'Failed to dissolve Soul Tether');
  }
}

/**
 * POST /api/magic/soul-tether/sineating/request/
 *
 * Sinner initiates a Sineating offer. Returns the SineatingOffer payload so the
 * Sineater can respond via /sineating/respond/.
 */
export async function requestSineating(body: SineatingRequest): Promise<SineatingOffer> {
  const res = await apiFetch(`${SOUL_TETHER_URL}/sineating/request/`, {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    await parseErrorDetail(res, 'Failed to send Sineating request');
  }

  return res.json() as Promise<SineatingOffer>;
}

/**
 * POST /api/magic/soul-tether/sineating/respond/
 *
 * Sineater accepts or declines a pending Sineating offer (units_accepted=0 = decline).
 * Returns SineatingResult with the outcome.
 */
export async function respondToSineating(body: SineatingRespondRequest): Promise<SineatingResult> {
  const res = await apiFetch(`${SOUL_TETHER_URL}/sineating/respond/`, {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    await parseErrorDetail(res, 'Failed to respond to Sineating offer');
  }

  return res.json() as Promise<SineatingResult>;
}

/**
 * POST /api/magic/soul-tether/rescue/
 *
 * Sineater performs the rescue ritual on the Sinner (stage 3+ only).
 * Returns RescueOutcome with severity_reduced, stage changes, and strain taken.
 */
export async function performRescue(body: RescueRequest): Promise<RescueOutcome> {
  const res = await apiFetch(`${SOUL_TETHER_URL}/rescue/`, {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    await parseErrorDetail(res, 'Failed to perform Soul Tether rescue');
  }

  return res.json() as Promise<RescueOutcome>;
}

/**
 * POST /api/magic/soul-tether/stage-advance/respond/
 *
 * Sineater responds to a stage-advance bonus offer (units_committed=0 = decline).
 * Returns StageAdvanceBonusResult with the outcome.
 */
export async function respondToStageAdvance(
  body: StageAdvanceRespondRequest
): Promise<StageAdvanceBonusResult> {
  const res = await apiFetch(`${SOUL_TETHER_URL}/stage-advance/respond/`, {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    await parseErrorDetail(res, 'Failed to respond to stage-advance offer');
  }

  return res.json() as Promise<StageAdvanceBonusResult>;
}

// ---------------------------------------------------------------------------
// Thread reads
// ---------------------------------------------------------------------------

/**
 * GET /api/magic/threads/
 *
 * Returns threads the requesting account owns (staff can see all), excluding
 * soft-retired rows.
 */
export async function getThreads(): Promise<PaginatedThreadList> {
  const res = await apiFetch(`${THREADS_URL}/`);
  if (!res.ok) throw new Error('Failed to load threads');
  return res.json() as Promise<PaginatedThreadList>;
}

// ---------------------------------------------------------------------------
// CharacterResonance reads
// ---------------------------------------------------------------------------

/**
 * GET /api/magic/character-resonances/
 *
 * Returns CharacterResonance rows scoped to the requesting account. When
 * ``characterSheetId`` is provided, narrows the response to that one
 * character — required for callers operating on a single character so
 * users with alts don't see a mixed list. Used by ResonancePickerField,
 * the thread hub/detail pages, and the soul-tether dialogs.
 */
export async function getCharacterResonances(
  characterSheetId?: number
): Promise<CharacterResonance[]> {
  const url =
    characterSheetId != null
      ? `${CHAR_RESONANCES_URL}/?character_sheet=${characterSheetId}`
      : `${CHAR_RESONANCES_URL}/`;
  const res = await apiFetch(url);
  if (!res.ok) throw new Error('Failed to load character resonances');
  return res.json() as Promise<CharacterResonance[]>;
}

// ---------------------------------------------------------------------------
// Pending offer detail reads (used for refresh after mutation)
// ---------------------------------------------------------------------------

/**
 * GET /api/magic/soul-tether/sineating/pending/{id}/
 */
export async function getPendingSineatingOffer(id: number): Promise<SineatingPendingOffer> {
  const res = await apiFetch(`${SOUL_TETHER_URL}/sineating/pending/${id}/`);
  if (!res.ok) throw new Error(`Failed to load Sineating offer ${id}`);
  return res.json() as Promise<SineatingPendingOffer>;
}

/**
 * GET /api/magic/soul-tether/stage-advance/pending/{id}/
 */
export async function getPendingStageAdvanceOffer(id: number): Promise<PendingStageAdvanceOffer> {
  const res = await apiFetch(`${SOUL_TETHER_URL}/stage-advance/pending/${id}/`);
  if (!res.ok) throw new Error(`Failed to load stage-advance offer ${id}`);
  return res.json() as Promise<PendingStageAdvanceOffer>;
}

// ---------------------------------------------------------------------------
// Tether bond enumeration
// ---------------------------------------------------------------------------

/**
 * Fetch tether bonds where myCharacterSheetId appears on either side.
 *
 * The relationships endpoint filters by a single source OR target, not both
 * at once, so we issue two requests and merge. Deduplication by `id` guards
 * against any edge cases.
 *
 * Returns an array of TetherBond — one entry per CharacterRelationship row
 * where is_soul_tether=true and the caller's sheet is source or target.
 */
export async function getMyTetherBonds(myCharacterSheetId: number): Promise<TetherBond[]> {
  const base = `${RELATIONSHIPS_URL}/?is_soul_tether=true&page_size=100`;

  const [asSourceRes, asTargetRes] = await Promise.all([
    apiFetch(`${base}&source=${myCharacterSheetId}`),
    apiFetch(`${base}&target=${myCharacterSheetId}`),
  ]);

  if (!asSourceRes.ok) throw new Error('Failed to load tether bonds (source query)');
  if (!asTargetRes.ok) throw new Error('Failed to load tether bonds (target query)');

  type RelRow = {
    id: number;
    source: number;
    source_name: string;
    target: number;
    target_name: string;
    soul_tether_role: string;
  };

  type PaginatedResult = { results?: RelRow[] } | RelRow[];

  const [sourceData, targetData] = (await Promise.all([
    asSourceRes.json(),
    asTargetRes.json(),
  ])) as [PaginatedResult, PaginatedResult];

  function extractRows(data: PaginatedResult): RelRow[] {
    if (Array.isArray(data)) return data;
    return data.results ?? [];
  }

  const allRows = [...extractRows(sourceData), ...extractRows(targetData)];

  // Deduplicate by relationship id
  const seen = new Set<number>();
  const bonds: TetherBond[] = [];

  for (const row of allRows) {
    if (seen.has(row.id)) continue;
    seen.add(row.id);

    const bondedOnTarget = row.source === myCharacterSheetId;
    bonds.push({
      relationship_id: row.id,
      bonded_character_sheet_id: bondedOnTarget ? row.target : row.source,
      bonded_character_name: bondedOnTarget ? row.target_name : row.source_name,
      soul_tether_role: row.soul_tether_role,
    });
  }

  return bonds;
}

// ---------------------------------------------------------------------------
// Thread Hub Summary
// ---------------------------------------------------------------------------

/**
 * GET /api/magic/thread-hub-summary/
 *
 * Returns balances, ready/near-lock/blocked thread ids, and weaving eligibility
 * for the acting character. Pass characterSheetId for alt-guard disambiguation.
 */
export async function getThreadHubSummary(characterSheetId?: number): Promise<ThreadHubSummary> {
  const url = characterSheetId
    ? `${THREAD_HUB_SUMMARY_URL}?character_sheet_id=${characterSheetId}`
    : THREAD_HUB_SUMMARY_URL;
  const res = await apiFetch(url);
  if (!res.ok) throw new Error('Failed to load thread hub summary');
  return res.json() as Promise<ThreadHubSummary>;
}

// ---------------------------------------------------------------------------
// Thread CRUD + actions
// ---------------------------------------------------------------------------

/**
 * GET /api/magic/threads/{id}/
 *
 * Returns the Thread with the given PK.
 */
export async function getThread(id: number): Promise<Thread> {
  const res = await apiFetch(`${THREADS_URL}/${id}/`);
  if (!res.ok) throw new Error(`Failed to load thread ${id}`);
  return res.json() as Promise<Thread>;
}

/**
 * POST /api/magic/threads/
 *
 * Weaves a new Thread for the given character/resonance/target combination.
 */
export async function weaveThread(body: WeaveThreadRequest): Promise<Thread> {
  const res = await apiFetch(`${THREADS_URL}/`, {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    await parseErrorDetail(res, 'Failed to weave thread');
  }
  return res.json() as Promise<Thread>;
}

/**
 * PATCH /api/magic/threads/{id}/
 *
 * Partially updates the thread's narrative fields (name, description).
 */
export async function patchThreadNarrative(id: number, body: PatchThreadRequest): Promise<Thread> {
  const res = await apiFetch(`${THREADS_URL}/${id}/`, {
    method: 'PATCH',
    headers: jsonHeaders(),
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    await parseErrorDetail(res, `Failed to update thread ${id}`);
  }
  return res.json() as Promise<Thread>;
}

/**
 * DELETE /api/magic/threads/{id}/
 *
 * Soft-retires the thread. Returns no body on success (204).
 */
export async function retireThread(id: number): Promise<void> {
  const res = await apiFetch(`${THREADS_URL}/${id}/`, {
    method: 'DELETE',
  });
  if (!res.ok) {
    await parseErrorDetail(res, `Failed to retire thread ${id}`);
  }
}

/**
 * POST /api/magic/threads/{id}/cross_xp_lock/
 *
 * Spends XP to cross an XP-lock boundary on the thread.
 * Returns {thread_id, unlocked_level, xp_spent} on success.
 */
export async function crossXPLock(
  threadId: number,
  body: CrossXPLockRequest
): Promise<CrossXPLockResponse> {
  const res = await apiFetch(`${THREADS_URL}/${threadId}/cross_xp_lock/`, {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    await parseErrorDetail(res, `Failed to cross XP lock on thread ${threadId}`);
  }
  return res.json() as Promise<CrossXPLockResponse>;
}

// ---------------------------------------------------------------------------
// Imbue Thread
//
// Imbuing is a SERVICE ritual — POST /api/magic/rituals/perform/ with kwargs
// { thread_id, amount }. getImbuingRitualId() looks up the Ritual whose
// service_function_path contains 'spend_resonance_for_imbuing'.
// ---------------------------------------------------------------------------

const _IMBUING_SERVICE_PATH = 'spend_resonance_for_imbuing';

/**
 * @internal
 * Module-level cache for the imbuing ritual id.
 * Reset in tests via __resetImbuingRitualIdCacheForTests().
 */
let _imbuingRitualIdCache: number | null = null;

/**
 * Exported ONLY for use in beforeEach in test files. Do not call in production code.
 */
export function __resetImbuingRitualIdCacheForTests(): void {
  _imbuingRitualIdCache = null;
}

/**
 * Resolves the Ritual PK whose service_function_path wraps spend_resonance_for_imbuing.
 * Result is cached in module scope.
 */
async function getImbuingRitualId(): Promise<number> {
  if (_imbuingRitualIdCache !== null) return _imbuingRitualIdCache;

  const paginatedList = await getRituals();
  const rituals = paginatedList.results ?? [];

  // The Ritual schema omits service_function_path from generated types (it is
  // server-internal); cast through unknown to access the field safely.
  const imbuing = rituals.find((r) => {
    const raw = r as unknown as { service_function_path?: string };
    return (
      typeof raw.service_function_path === 'string' &&
      raw.service_function_path.includes(_IMBUING_SERVICE_PATH)
    );
  });

  if (!imbuing) {
    throw new Error('Imbuing ritual not found — ensure the Ritual seed exists on this server');
  }

  _imbuingRitualIdCache = imbuing.id;
  return imbuing.id;
}

/**
 * Imbue a thread by spending resonance via the imbuing service ritual.
 *
 * Internally resolves the imbuing ritual id (cached after first call) and
 * dispatches POST /api/magic/rituals/perform/ with kwargs { thread_id, amount }.
 */
export async function imbueThread(body: ImbueRequest): Promise<ImbueResponse> {
  const { performRitual } = await import('@/rituals/api');
  const res = await performRitual({
    ritual_id: body.ritual_id,
    character_sheet_id: body.character_sheet_id,
    kwargs: body.kwargs,
  });
  // performRitual already throws on error; map to our response shape.
  // The backend wraps the ThreadImbueResult dataclass in `result`.
  const raw = res as unknown as {
    message?: string;
    result?: {
      resonance_spent?: number;
      developed_points_added?: number;
      levels_gained?: number;
      new_level?: number;
      new_developed_points?: number;
      blocked_by?: string;
    };
  };
  return {
    success: true,
    message: raw.message,
    resonance_spent: raw.result?.resonance_spent,
    developed_points_added: raw.result?.developed_points_added,
    levels_gained: raw.result?.levels_gained,
    new_level: raw.result?.new_level,
    new_developed_points: raw.result?.new_developed_points,
    blocked_by: raw.result?.blocked_by,
  };
}

/**
 * Resolve the imbuing ritual id and perform imbuing in one call.
 * This is the preferred API for UI usage.
 */
export async function imbueThreadAuto(
  characterSheetId: number,
  threadId: number,
  amount: number
): Promise<ImbueResponse> {
  const ritualId = await getImbuingRitualId();
  return imbueThread({
    ritual_id: ritualId,
    character_sheet_id: characterSheetId,
    kwargs: { thread_id: threadId, amount },
  });
}

// ---------------------------------------------------------------------------
// Pull Preview
// ---------------------------------------------------------------------------

/**
 * POST /api/magic/thread-pull-preview/
 *
 * Returns a dry-run of pull effects without committing resonance.
 * Use this for user-facing previews; debounce at the call site.
 */
export async function previewPull(body: PullPreviewRequest): Promise<PullPreviewResponse> {
  const res = await apiFetch(THREAD_PULL_PREVIEW_URL, {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    await parseErrorDetail(res, 'Failed to preview pull effects');
  }
  return res.json() as Promise<PullPreviewResponse>;
}

// ---------------------------------------------------------------------------
// Pull Commit
// ---------------------------------------------------------------------------

/**
 * POST /api/magic/thread-pull-commit/
 *
 * Commits the pull: spends resonance and applies effects.
 */
export async function commitPull(body: PullCommitRequest): Promise<PullCommitResponse> {
  const res = await apiFetch(THREAD_PULL_COMMIT_URL, {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    await parseErrorDetail(res, 'Failed to commit pull');
  }
  return res.json() as Promise<PullCommitResponse>;
}

// ---------------------------------------------------------------------------
// Teaching Offers
// ---------------------------------------------------------------------------

/**
 * GET /api/magic/teaching-offers/
 *
 * Returns paginated ThreadWeavingTeachingOffer records visible to the caller.
 */
export async function getTeachingOffers(): Promise<PaginatedTeachingOfferList> {
  const res = await apiFetch(`${TEACHING_OFFERS_URL}/`);
  if (!res.ok) throw new Error('Failed to load teaching offers');
  return res.json() as Promise<PaginatedTeachingOfferList>;
}

/**
 * POST /api/magic/teaching-offers/{id}/accept/
 *
 * Accepts a ThreadWeavingTeachingOffer on behalf of the requesting learner.
 * Returns {id, unlock_id, xp_spent} for the new CharacterThreadWeavingUnlock.
 */
export async function acceptTeachingOffer(
  offerId: number,
  body?: AcceptTeachingOfferRequest
): Promise<AcceptTeachingOfferResponse> {
  const res = await apiFetch(`${TEACHING_OFFERS_URL}/${offerId}/accept/`, {
    method: 'POST',
    headers: jsonHeaders(),
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    await parseErrorDetail(res, `Failed to accept teaching offer ${offerId}`);
  }
  return res.json() as Promise<AcceptTeachingOfferResponse>;
}

// ---------------------------------------------------------------------------
// Rooms by property
// ---------------------------------------------------------------------------

/**
 * GET /api/magic/rooms-by-property/?property_id=N&property_id=M...
 *
 * Returns rooms that have all specified property tags.
 * Used by the thread-weaving room picker.
 */
export async function getRoomsByProperty(propertyIds: number[]): Promise<RoomBrief[]> {
  const params = propertyIds.map((id) => `property_id=${id}`).join('&');
  const url = params ? `${ROOMS_BY_PROPERTY_URL}?${params}` : ROOMS_BY_PROPERTY_URL;
  const res = await apiFetch(url);
  if (!res.ok) throw new Error('Failed to load rooms by property');
  return res.json() as Promise<RoomBrief[]>;
}

// ---------------------------------------------------------------------------
// Technique detail
// ---------------------------------------------------------------------------

/**
 * GET /api/magic/techniques/{id}/
 *
 * Returns a single Technique with intensity, control, anima_cost and other stats.
 * Used by ActionDeclarationCard to render the I/C chip and cost preview.
 */
export async function getTechnique(id: number): Promise<Technique> {
  const res = await apiFetch(`${TECHNIQUES_URL}/${id}/`);
  if (!res.ok) throw new Error(`Failed to load technique ${id}`);
  return res.json() as Promise<Technique>;
}

// ---------------------------------------------------------------------------
// Applicable Pulls
// ---------------------------------------------------------------------------

const APPLICABLE_PULLS_URL = '/api/magic/applicable-pulls/';

/**
 * POST /api/magic/applicable-pulls/
 *
 * Returns per-thread applicability rows for the given action context.
 * Each row: { thread_id, applicable, inapplicable_reason }.
 * Designed to be called from useApplicablePulls; do not call directly in components.
 */
export async function fetchApplicablePulls(
  body: ApplicablePullsRequest
): Promise<ThreadApplicability[]> {
  const res = await apiFetch(APPLICABLE_PULLS_URL, {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    await parseErrorDetail(res, 'Failed to fetch applicable pulls');
  }
  return res.json() as Promise<ThreadApplicability[]>;
}

// ---------------------------------------------------------------------------
// Character Anima
// ---------------------------------------------------------------------------

const CHARACTER_ANIMA_URL = '/api/magic/character-anima/';

/** Shape of CharacterAnima records returned by GET /api/magic/character-anima/. */
export interface CharacterAnimaRecord {
  id: number;
  character: number;
  current: number;
  maximum: number;
  last_recovery: string | null;
}

/**
 * GET /api/magic/character-anima/?character=<characterId>
 *
 * Returns CharacterAnima records visible to the authenticated user,
 * narrowed to the given character (ObjectDB PK).
 *
 * The response is a paginated list; we return the first result's record
 * since each character has at most one CharacterAnima row.
 */
export async function getCharacterAnima(
  characterId: number
): Promise<CharacterAnimaRecord | null> {
  const res = await apiFetch(`${CHARACTER_ANIMA_URL}?character=${characterId}`);
  if (!res.ok) throw new Error(`Failed to load anima for character ${characterId}`);
  const data = (await res.json()) as { results?: CharacterAnimaRecord[] } | CharacterAnimaRecord[];
  // Handle both paginated (results array) and bare array responses.
  const list: CharacterAnimaRecord[] = Array.isArray(data)
    ? data
    : ((data as { results?: CharacterAnimaRecord[] }).results ?? []);
  return list[0] ?? null;
}

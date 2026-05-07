/**
 * Magic API functions
 *
 * Covers Soul Tether endpoints, Thread reads, and CharacterResonance reads.
 * Uses apiFetch from @/evennia_replacements/api.
 *
 * Note: Soul Tether *formation* (acceptance) goes through
 * POST /api/magic/rituals/perform/ via usePerformRitual in the rituals module.
 */

import { apiFetch } from '@/evennia_replacements/api';
import type {
  CharacterResonance,
  DissolveRequest,
  PaginatedPendingStageAdvanceOfferList,
  PaginatedSineatingPendingOfferList,
  PaginatedThreadList,
  PendingStageAdvanceOffer,
  RescueOutcome,
  RescueRequest,
  SineatingOffer,
  SineatingPendingOffer,
  SineatingRequest,
  SineatingRespondRequest,
  SineatingResult,
  SoulTetherDetail,
  StageAdvanceBonusResult,
  StageAdvanceRespondRequest,
  TetherBond,
} from './types';

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
 * Returns all CharacterResonance rows for the requesting account's characters.
 * Used by ResonancePickerField and similar UI surfaces.
 */
export async function getCharacterResonances(): Promise<CharacterResonance[]> {
  const res = await apiFetch(`${CHAR_RESONANCES_URL}/`);
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

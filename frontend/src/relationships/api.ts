/**
 * Relationships API functions (#2031, #2159)
 *
 * Covers the read surface backing the commend button on relationship
 * writeups: GET /api/relationships/relationship-updates/ (tenure-scoped —
 * only SHARED/PUBLIC writeups where the requesting user's account currently
 * holds tenure over the parent relationship's target, i.e. the writeup's
 * commendable subject; see RelationshipUpdateViewSet.get_queryset) and POST
 * .../kudos/ to commend one.
 *
 * Also covers the four positive relationship-building write actions
 * (`first_impression`/`develop`/`capstone`/`redistribute`, all on the same
 * `/api/relationships/relationship-updates/` viewset), the track catalog
 * (`GET /api/relationships/tracks/`), and a narrow read of the caller's own
 * relationship toward one target (`GET /api/relationships/relationships/
 * ?target=<CharacterSheet pk>`, scoped server-side by
 * `CharacterRelationshipViewSet.get_queryset` to rows the caller's tenure-owned
 * characters authored) — used by `RelationshipWriteupDialog` and the
 * card-drawer quick action to branch between impression/development mode.
 */

import { apiFetch } from '@/evennia_replacements/api';
import type { components } from '@/generated/api';

export type RelationshipWriteup = components['schemas']['RelationshipUpdate'];
export type GiveWriteupKudosRequest = components['schemas']['WriteupKudosWriteRequest'];
export type RelationshipTrack = components['schemas']['RelationshipTrack'];
export type CharacterRelationshipList = components['schemas']['CharacterRelationshipList'];
export type FirstImpressionWriteRequest = components['schemas']['FirstImpressionWriteRequest'];
export type DevelopmentWriteRequest = components['schemas']['DevelopmentWriteRequest'];
export type CapstoneWriteRequest = components['schemas']['CapstoneWriteRequest'];
export type RedistributeWriteRequest = components['schemas']['RedistributeWriteRequest'];

/**
 * Runtime shape of every write action's response.
 *
 * The generated OpenAPI response schemas for `first_impression`/`develop`/
 * `capstone`/`redistribute` (`FirstImpressionWrite` etc.) are wrong — drf-spectacular
 * infers them from the request serializer since `RelationshipUpdateViewSet`'s
 * actions don't declare a response serializer. The views actually return
 * `{success, message, data}` (see `_run_action` in `world/relationships/views.py`),
 * matching the kudos/complaint feedback actions.
 */
export interface RelationshipWriteResult {
  success: boolean;
  message: string;
  data: Record<string, unknown>;
}

const RELATIONSHIP_UPDATES_URL = '/api/relationships/relationship-updates';
const RELATIONSHIPS_URL = '/api/relationships/relationships';
const RELATIONSHIP_TRACKS_URL = '/api/relationships/tracks';

function jsonHeaders(): HeadersInit {
  return { 'Content-Type': 'application/json' };
}

/**
 * GET /api/relationships/relationship-updates/
 *
 * Returns SHARED/PUBLIC writeups where the requesting user's account holds
 * tenure over the subject character — the writeups the caller may commend.
 * This is NOT a general writeup browser: the endpoint is scoped to the
 * requesting user's tenure-owned characters, so it only makes sense to call
 * this while viewing one of the caller's own sheets.
 *
 * Pass `subjectCharacterId` (the viewed CharacterSheet pk) to narrow to that
 * one owned character's writeups — required for accounts with more than one
 * owned character, so a sibling character's writeups don't get mislabeled as
 * belonging to the one currently being viewed (fix wave, Finding 2).
 */
export async function getMyWriteups(subjectCharacterId?: number): Promise<RelationshipWriteup[]> {
  const params = new URLSearchParams({ page_size: '100' });
  if (subjectCharacterId != null) {
    params.set('subject_character', String(subjectCharacterId));
  }
  const res = await apiFetch(`${RELATIONSHIP_UPDATES_URL}/?${params.toString()}`);
  if (!res.ok) throw new Error('Failed to load relationship writeups');
  const data = (await res.json()) as { results?: RelationshipWriteup[] } | RelationshipWriteup[];
  return Array.isArray(data) ? data : (data.results ?? []);
}

/**
 * Parse an Action-backed endpoint's failure body: `{success: false, message}`.
 *
 * This is NOT the DRF `{detail}` shape `readErrorDetail` (lib/errors) parses,
 * so that helper is not reusable here — the kudos/complaint/first_impression/
 * develop/capstone/redistribute actions all return their own `result.message`
 * from the underlying Action, not a DRF exception. Shared by the kudos call
 * below and the four relationship-building write actions (#2159).
 */
async function readActionErrorMessage(res: Response, fallback: string): Promise<never> {
  let message = fallback;
  try {
    const data = (await res.json()) as { message?: string };
    if (typeof data.message === 'string' && data.message.trim()) {
      message = data.message;
    }
  } catch {
    // body wasn't JSON; keep the fallback
  }
  throw new Error(message);
}

/**
 * POST /api/relationships/relationship-updates/kudos/
 *
 * The writeup's subject commends it, awarding the author kudos points.
 * Rejected with the exact `WriteupFeedbackError.user_message` on 400
 * (already-commended, non-subject, private writeup, etc).
 */
export async function giveWriteupKudos(body: GiveWriteupKudosRequest): Promise<void> {
  const res = await apiFetch(`${RELATIONSHIP_UPDATES_URL}/kudos/`, {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    await readActionErrorMessage(res, 'Failed to commend this writeup');
  }
}

/**
 * GET /api/relationships/tracks/
 *
 * The full relationship-track catalog (with nested tiers) — unpaginated
 * (`RelationshipTrackViewSet.pagination_class = None`). Feeds every track
 * picker in `RelationshipWriteupDialog`.
 */
export async function getRelationshipTracks(): Promise<RelationshipTrack[]> {
  const res = await apiFetch(`${RELATIONSHIP_TRACKS_URL}/`);
  if (!res.ok) throw new Error('Failed to load relationship tracks');
  return (await res.json()) as RelationshipTrack[];
}

/**
 * GET /api/relationships/relationships/?target=<CharacterSheet pk>
 *
 * The caller's own outbound relationship(s) toward one target character.
 * `CharacterRelationshipViewSet.get_queryset` is already scoped server-side
 * to rows whose `source` belongs to one of the caller's tenure-owned
 * characters (plus a universally-readable `is_soul_tether` carve-out — see
 * ADR-0117) — this call only narrows that scoped set to one `target`, it
 * cannot widen it. Used to branch `RelationshipWriteupDialog` between
 * development mode (a relationship already exists) and impression mode
 * (none yet).
 */
export async function getMyRelationshipToTarget(
  targetCharacterSheetId: number
): Promise<CharacterRelationshipList[]> {
  const params = new URLSearchParams({ target: String(targetCharacterSheetId) });
  const res = await apiFetch(`${RELATIONSHIPS_URL}/?${params.toString()}`);
  if (!res.ok) throw new Error('Failed to load relationship');
  const data = (await res.json()) as
    | { results?: CharacterRelationshipList[] }
    | CharacterRelationshipList[];
  return Array.isArray(data) ? data : (data.results ?? []);
}

async function postWriteAction(
  action: 'first_impression' | 'develop' | 'capstone' | 'redistribute',
  body: unknown,
  fallback: string
): Promise<RelationshipWriteResult> {
  const res = await apiFetch(`${RELATIONSHIP_UPDATES_URL}/${action}/`, {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    await readActionErrorMessage(res, fallback);
  }
  return (await res.json()) as RelationshipWriteResult;
}

/** POST .../first_impression/ — unilateral, creates a pending relationship. */
export async function postFirstImpression(
  body: FirstImpressionWriteRequest
): Promise<RelationshipWriteResult> {
  return postWriteAction('first_impression', body, 'Failed to record this impression');
}

/** POST .../develop/ — solidifies temporary points into permanent developed points. */
export async function postDevelopment(
  body: DevelopmentWriteRequest
): Promise<RelationshipWriteResult> {
  return postWriteAction('develop', body, 'Failed to record this development');
}

/** POST .../capstone/ — records a monumental relationship moment. */
export async function postCapstone(body: CapstoneWriteRequest): Promise<RelationshipWriteResult> {
  return postWriteAction('capstone', body, 'Failed to record this capstone');
}

/** POST .../redistribute/ — moves developed points between tracks. */
export async function postRedistribute(
  body: RedistributeWriteRequest
): Promise<RelationshipWriteResult> {
  return postWriteAction('redistribute', body, 'Failed to redistribute points');
}

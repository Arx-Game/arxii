/**
 * Ties: the read and write surface for one side of a relationship (#3957).
 *
 * A tie is two people; this module speaks for ONE side of it — the caller's own, or
 * whichever side a page was opened on. Everything the viewer is allowed to know is
 * decided server-side and arrives already shaped: `audience` says which of the four
 * views came back, and a value a third party may not have (`depth`, `next_tier_threshold`,
 * `breakdown`, `thread`, `ap_this_week`) arrives as null rather than as a number the UI
 * would then have to decide whether to print. The frontend never re-derives any of it.
 *
 * A tie with no open Public label simply does not exist for a third party: `getTie`
 * answers 404, never 403, so a tie's mere existence is never leaked by the shape of a
 * refusal. The page renders that as "not found".
 *
 * The seven writes all POST to their own verb on the tie collection and converge on
 * `action.run()` server-side, so they all answer with the same `{success, message, data}`
 * envelope and all report a refusal through `message`.
 */

import { apiFetch } from '@/evennia_replacements/api';
import type { components } from '@/generated/api';

export type Tie = components['schemas']['Tie'];
export type TieLabel = components['schemas']['RelationshipLabel'];
export type TieStreamItem = components['schemas']['TieStreamItem'];
export type TieThread = components['schemas']['TieThread'];
export type DepthBreakdown = components['schemas']['DepthBreakdown'];
export type RelationshipType = components['schemas']['RelationshipType'];
export type TieWriteResult = components['schemas']['TieWriteResult'];
export type Awareness = components['schemas']['AwarenessEnum'];
export type RelationshipTypeFamily = components['schemas']['FamilyEnum'];

export type DeclareLabelBody = components['schemas']['DeclareWriteRequest'];
export type ShiftLabelBody = components['schemas']['ShiftWriteRequest'];
export type EndLabelBody = components['schemas']['LabelWriteRequest'];
export type AwarenessBody = components['schemas']['AwarenessWriteRequest'];
export type AllocationBody = components['schemas']['AllocationWriteRequest'];
export type AdvanceTierBody = components['schemas']['AdvanceWriteRequest'];
export type SummaryBody = components['schemas']['SummaryWriteRequest'];

const TIES_URL = '/api/relationships/relationships';
const TYPES_URL = '/api/relationships/types';

function jsonHeaders(): HeadersInit {
  return { 'Content-Type': 'application/json' };
}

/**
 * Parse an Action-backed endpoint's failure body: `{success: false, message}`.
 *
 * NOT the DRF `{detail}` shape `readErrorDetail` (lib/errors) parses — every tie write
 * returns its underlying Action's own `result.message`, which is the sentence the
 * player is meant to read ("You have already made that public.").
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

/** Raised by `getTie` for a tie the viewer may not see — which is indistinguishable, */
/** deliberately, from one that does not exist. */
export class TieNotFoundError extends Error {
  constructor() {
    super('Tie not found');
    this.name = 'TieNotFoundError';
  }
}

/**
 * GET /api/relationships/relationships/{id}/
 *
 * One side, shaped for whoever is asking. A 404 here is the audience rule, not an
 * error to report: the caller renders the page's not-found treatment.
 */
export async function getTie(relationshipId: number): Promise<Tie> {
  const res = await apiFetch(`${TIES_URL}/${relationshipId}/`);
  if (res.status === 404) throw new TieNotFoundError();
  if (!res.ok) throw new Error('Failed to load this tie');
  return (await res.json()) as Tie;
}

/**
 * GET /api/relationships/relationships/
 *
 * The caller's own outbound sides, always shaped as their OWNER view — the list
 * endpoint is scoped server-side and cannot be widened by a query param.
 */
export async function listMyTies(): Promise<Tie[]> {
  const res = await apiFetch(`${TIES_URL}/?page_size=100`);
  if (!res.ok) throw new Error('Failed to load your ties');
  const data = (await res.json()) as { results?: Tie[] } | Tie[];
  return Array.isArray(data) ? data : (data.results ?? []);
}

/**
 * GET /api/relationships/relationships/{id}/stream/
 *
 * The journal entries and shared scenes between the two sides, already filtered to what
 * this viewer may read. Unpaginated (`pagination_class = None` on the action).
 */
export async function getTieStream(relationshipId: number): Promise<TieStreamItem[]> {
  const res = await apiFetch(`${TIES_URL}/${relationshipId}/stream/`);
  if (res.status === 404) throw new TieNotFoundError();
  if (!res.ok) throw new Error('Failed to load this tie');
  const data = (await res.json()) as { results?: TieStreamItem[] } | TieStreamItem[];
  return Array.isArray(data) ? data : (data.results ?? []);
}

/**
 * GET /api/relationships/types/
 *
 * The whole label catalogue — eighteen-odd authored rows, so one page of 100 is the
 * whole thing and the picker groups it client-side by `family`.
 */
export async function getRelationshipTypes(): Promise<RelationshipType[]> {
  const res = await apiFetch(`${TYPES_URL}/?page_size=100`);
  if (!res.ok) throw new Error('Failed to load relationship types');
  const data = (await res.json()) as { results?: RelationshipType[] } | RelationshipType[];
  return Array.isArray(data) ? data : (data.results ?? []);
}

async function postTieAction(
  verb: 'declare' | 'shift' | 'end' | 'awareness' | 'allocation' | 'advance' | 'summary',
  body: unknown,
  fallback: string
): Promise<TieWriteResult> {
  const res = await apiFetch(`${TIES_URL}/${verb}/`, {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    await readActionErrorMessage(res, fallback);
  }
  return (await res.json()) as TieWriteResult;
}

/** POST .../declare/ — name a type on the caller's side. Free, and one-sided. */
export async function declareLabel(body: DeclareLabelBody): Promise<TieWriteResult> {
  return postTieAction('declare', body, 'Failed to declare this label');
}

/** POST .../shift/ — end one label and declare its replacement, which remembers it. */
export async function shiftLabel(body: ShiftLabelBody): Promise<TieWriteResult> {
  return postTieAction('shift', body, 'Failed to change this label');
}

/** POST .../end/ — stamp `ended_at`. The row stays; nothing here deletes. */
export async function endLabel(body: EndLabelBody): Promise<TieWriteResult> {
  return postTieAction('end', body, 'Failed to end this label');
}

/** POST .../awareness/ — private → clandestine → public, forward only. */
export async function advanceAwareness(body: AwarenessBody): Promise<TieWriteResult> {
  return postTieAction('awareness', body, 'Failed to change this label');
}

/** POST .../allocation/ — this week's AP for the whole tie, not per label. */
export async function setTieAllocation(body: AllocationBody): Promise<TieWriteResult> {
  return postTieAction('allocation', body, 'Failed to set AP for this tie');
}

/** POST .../advance/ — claim the next tier against a capstone entry, for XP. */
export async function advanceTier(body: AdvanceTierBody): Promise<TieWriteResult> {
  return postTieAction('advance', body, 'Failed to advance this tier');
}

/** POST .../summary/ — the paragraph on the tie page, in the owner's own words. */
export async function setTieSummary(body: SummaryBody): Promise<TieWriteResult> {
  return postTieAction('summary', body, 'Failed to save this summary');
}

/**
 * GET /api/personas/?character_sheet=
 *
 * The tie writes name their target by PERSONA (`_resolve_target` in the viewset), while
 * every tie payload names it by CharacterSheet — so one lookup stands between reading a
 * tie and writing to it. It lives here rather than in a page because the weave wizard
 * asks the same question about the same people.
 *
 * Returns the sheet's primary persona, falling back to its first: a character with no
 * primary is a data state, not a reason to refuse the write.
 */
export async function getPersonaIdForSheet(characterSheetId: number): Promise<number | null> {
  const res = await apiFetch(`/api/personas/?character_sheet=${characterSheetId}&page_size=50`);
  if (!res.ok) return null;
  const data = (await res.json()) as {
    results?: Array<{ id: number; persona_type: string }>;
  };
  const personas = data.results ?? [];
  return personas.find((p) => p.persona_type === 'primary')?.id ?? personas[0]?.id ?? null;
}

/** Exactly one of the two target keys the write serializers demand (#3957). */
export interface TieTargetRef {
  target_persona_id?: number;
  target_companion_id?: number;
}

/**
 * Which side a tie write names. The serializers reject both keys and reject neither, so
 * this is the one place that picks: a companion tie by companion, everything else by the
 * other side's persona.
 */
export function tieTargetRef(tie: Tie, targetPersonaId: number | null): TieTargetRef {
  if (tie.target_companion != null) return { target_companion_id: tie.target_companion };
  if (targetPersonaId != null) return { target_persona_id: targetPersonaId };
  return {};
}

/**
 * Whether a target ref names anybody yet.
 *
 * `tieTargetRef` answers `{}` while the persona lookup is in flight, or when it came back
 * empty. Posting that body earns "Provide exactly one of target_persona_id or
 * target_companion_id." from the serializer — a sentence written for a developer, which a
 * player must never be shown. So every write door is disabled until this is true, rather
 * than enabled and then apologising.
 */
export function hasTieTarget(target: TieTargetRef): boolean {
  return target.target_persona_id != null || target.target_companion_id != null;
}

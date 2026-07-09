/**
 * Relationships API functions (#2031)
 *
 * Covers the read surface backing the commend button on relationship
 * writeups: GET /api/relationships/relationship-updates/ (subject-scoped —
 * only SHARED/PUBLIC writeups where the requesting user's character is the
 * parent relationship's target, i.e. the writeup's commendable subject; see
 * RelationshipUpdateViewSet.get_queryset) and POST .../kudos/ to commend one.
 */

import { apiFetch } from '@/evennia_replacements/api';
import type { components } from '@/generated/api';

export type RelationshipWriteup = components['schemas']['RelationshipUpdate'];
export type GiveWriteupKudosRequest = components['schemas']['WriteupKudosWriteRequest'];

const RELATIONSHIP_UPDATES_URL = '/api/relationships/relationship-updates';

function jsonHeaders(): HeadersInit {
  return { 'Content-Type': 'application/json' };
}

/**
 * GET /api/relationships/relationship-updates/
 *
 * Returns SHARED/PUBLIC writeups where the requesting user's character is
 * the subject — the writeups the caller may commend. This is NOT a general
 * writeup browser: the endpoint is scoped to the requesting user, so it
 * only makes sense to call this while viewing the caller's own sheet.
 */
export async function getMyWriteups(): Promise<RelationshipWriteup[]> {
  const res = await apiFetch(`${RELATIONSHIP_UPDATES_URL}/?page_size=100`);
  if (!res.ok) throw new Error('Failed to load relationship writeups');
  const data = (await res.json()) as { results?: RelationshipWriteup[] } | RelationshipWriteup[];
  return Array.isArray(data) ? data : (data.results ?? []);
}

/**
 * Parse the kudos endpoint's failure body: `{success: false, message}`.
 *
 * This is NOT the DRF `{detail}` shape `readErrorDetail` (lib/errors) parses,
 * so that helper is not reusable here — the kudos/complaint actions return
 * their own `result.message` from the underlying Action, not a DRF exception.
 */
async function readKudosErrorMessage(res: Response, fallback: string): Promise<never> {
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
    await readKudosErrorMessage(res, 'Failed to commend this writeup');
  }
}

/**
 * Legend API client — deed detail, honors, and the honor action (#3466 Task 10).
 *
 * `DeedDetailSerializer`'s nested `persona`/`event` fields and `LegendHonorSerializer`'s
 * `honorer` field are plain-dict `SerializerMethodField`s that `drf-spectacular` can't
 * introspect — they come back as `{[key: string]: unknown}` in `generated/api.d.ts`, and
 * the `honor` action's operation is misdescribed there too (`requestBody: never`, a 200
 * response typed as `DeedDetail` instead of the actual 201 `LegendHonor`). Same precedent
 * as `frontend/src/journals/api.ts`: hand-authored from `task-9-report.md`'s documented
 * shapes rather than the generated operation types. `CanHonor` and the journal summary
 * type ARE precisely generated (plain serializer fields, no nested dict), so those two are
 * reused directly from `components['schemas']`.
 *
 * Keep these shapes in sync BY HAND with `src/world/societies/serializers.py` if the
 * backend changes.
 */

import { apiFetch } from '@/evennia_replacements/api';
import { readErrorDetail } from '@/lib/errors';
import type { components } from '@/generated/api';

/** `{allowed, reason, hares_required, value_added}` — see `task-9-report.md`. */
export type CanHonor = components['schemas']['CanHonor'];

/** `{id, title, body}` — a persona's public journal entry, inlined onto its honor. */
export type JournalSummary = components['schemas']['_JournalSummary'];

/** A persona's public face — id + display name only, never the account (#3466). */
export interface PersonaFace {
  id: number;
  name: string;
}

/** The legend event a deed is anchored under (minimal summary; null for unanchored deeds). */
export interface DeedEvent {
  id: number;
  title: string;
  base_value: number;
}

/** One paid, written testimony to a deed. */
export interface LegendHonor {
  id: number;
  honorer: PersonaFace;
  /** Legend actually contributed, after the event ceiling clamped it. */
  value_added: number;
  /** Denormalized Golden Hares count spent on this honor. */
  hares_spent: number;
  /** True when this honor is the one that created the deed. */
  established_deed: boolean;
  created_at: string;
  journal: JournalSummary;
}

export interface DeedDetail {
  id: number;
  title: string;
  description: string;
  persona: PersonaFace;
  base_value: number;
  /** Max total legend the anchoring event allows; null for an unanchored deed. */
  ceiling: number | null;
  /** `max(event.base_value - base_value, 0)`; null for an unanchored deed. */
  headroom: number | null;
  earned_at_level: number;
  event: DeedEvent | null;
  honors: LegendHonor[];
  can_honor: CanHonor;
}

export interface HonorDeedRequest {
  journal_title: string;
  journal_body: string;
}

/** GET /api/societies/deeds/{id}/ */
export async function fetchDeed(id: number): Promise<DeedDetail> {
  const res = await apiFetch(`/api/societies/deeds/${id}/`);
  if (!res.ok) {
    await readErrorDetail(res, 'Failed to load deed');
  }
  return res.json();
}

/**
 * POST /api/societies/deeds/{id}/honor/ — amplify this deed.
 *
 * The honoree is always the deed's own persona (server-chosen, never client-picked —
 * there is no implicit "pick one" selection here). A refusal (insufficient Hares,
 * already honored, at ceiling, no active persona, etc.) comes back as
 * `400 {detail: <HonorRefused.user_message>}`; `readErrorDetail` throws an `ApiError`
 * whose `message` is that string verbatim, for the caller to surface as-is.
 */
export async function honorDeed(id: number, body: HonorDeedRequest): Promise<LegendHonor> {
  const res = await apiFetch(`/api/societies/deeds/${id}/honor/`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    await readErrorDetail(res, 'Failed to honor this deed');
  }
  return res.json();
}

import type { Session } from '@/store/gameSlice';
import type { Interaction } from '@/scenes/types';
import { getThreadKey, countUnread } from '@/scenes/hooks/useThreading';
import { wsPayloadToInteraction } from '@/scenes/hooks/useSceneInteractions';
import type { MyRosterEntry } from '@/roster/types';
import { actingPersonaId } from '@/roster/persona';
import { classifyInteraction, type FeedKind } from './feedKinds';
import { feedItemKey, type FeedChip } from './feedChips';

/**
 * What the player's chips say should count (#3856): only interactions whose
 * kind sits under a chip that is on and set to wake, and never one the player
 * dismissed from their own view. Omitted, everything counts (the pre-chips
 * behaviour and what a caller with no preferences wants).
 */
export interface AttentionOptions {
  wakingKinds?: ReadonlySet<FeedKind>;
  dismissed?: ReadonlySet<string>;
}

function passesOptions(interaction: Interaction, options?: AttentionOptions): boolean {
  if (!options) return true;
  if (options.dismissed?.has(feedItemKey('interaction', interaction.id))) return false;
  return !options.wakingKinds || options.wakingKinds.has(classifyInteraction(interaction.mode));
}

export interface SessionAttention {
  /** Total unread across whisper threads + target threads aimed at `personaId`. */
  direct: number;
  /** True when any other thread has unread, or the legacy `session.unread` counter is set. */
  ambient: boolean;
}

/**
 * Two-tier attention derivation for one character's session (#2166 Decisions
 * 4a/4b). Pure and selector-side — no new Redux write path; reuses #2156/#2165's
 * `getThreadKey`/`countUnread` grouping and threshold rule against
 * `threadLastSeen`/`sceneBaselineId`.
 *
 * `direct` = total unread on `whisper:*` threads (a session only ever receives
 * whispers addressed to its own persona, so every whisper thread here already
 * targets this character) plus every unread interaction whose
 * `target_persona_ids` includes `personaId`, wherever it happens to be grouped.
 *
 * Direct is TARGET-aware, not thread-key-aware (#3787 final review, I1). It used
 * to read `key.startsWith('target:')`, which was the same answer back when the
 * `target:` key was the only way a row could name anyone. #3787 decision 5 then
 * keyed `action`/`outcome` rows to `scene:N` BEFORE that fallback, so that
 * grouping would not fragment one fight into a group per victim (decision 6
 * reuses this same `direct` tier for those rows). Reading the key would have
 * quietly demoted a blow aimed at you to `ambient` and left user story 8, "what
 * was aimed at me is findable when I come back", undelivered. Both decisions hold
 * once grouping goes by scene and direct goes by targeting.
 *
 * `countUnread` already excludes the viewer's own authored interactions, so a
 * thread containing only this persona's own poses contributes to neither tier, and
 * reusing it on the targeted SUBSET of a thread keeps one threshold rule rather
 * than a second copy of it. Both tiers require `personaId != null`: until the
 * roster resolves it, `countUnread` can't exclude the session's own authored
 * messages, so whisper/target unread routes to `ambient` instead (avoids a
 * pre-roster-load flicker where a session's own echoed whisper reads as
 * direct).
 *
 * `ambient` = true when any thread still has unread this persona was not named in
 * (room/place scroll, a scene thread whose blows landed on someone else), or the
 * legacy `session.unread` scalar (pre-#2156 sessions / non-interaction game
 * messages) is nonzero.
 *
 * `sinceId` (#3774) is the newest interaction the SERVER already counted for
 * this character (`MyRosterEntry.attention_as_of_id`). Anything at or below it
 * is dropped here, because the caller adds this result to the server's count:
 * without the watermark a whisper that arrived over the WebSocket and was then
 * included in the next roster refetch would badge twice. Omitted or null means
 * count everything, which is the pre-#3774 behavior and what a caller with no
 * server baseline wants. A `sinceId` of `0` is effect-equivalent to that, since
 * interaction ids start at 1 and every real id is `> 0` -- but it is not
 * structurally the same branch: it fails `sinceId == null` and is kept by the
 * `Number(id) > sinceId` comparison instead (review fold-in).
 */
export function sessionAttention(
  session: Session,
  personaId: number | null,
  sinceId?: number | null,
  options?: AttentionOptions
): SessionAttention {
  const interactions: Interaction[] = session.sceneInteractions
    .map(wsPayloadToInteraction)
    .filter((interaction) => sinceId == null || Number(interaction.id) > sinceId)
    .filter((interaction) => passesOptions(interaction, options));
  const byThread = new Map<string, Interaction[]>();
  for (const interaction of interactions) {
    const key = getThreadKey(interaction);
    const bucket = byThread.get(key);
    if (bucket) {
      bucket.push(interaction);
    } else {
      byThread.set(key, [interaction]);
    }
  }

  let direct = 0;
  let ambient = session.unread > 0;

  for (const [key, threadInteractions] of byThread) {
    const unread = countUnread(
      threadInteractions,
      key,
      session.threadLastSeen,
      personaId,
      session.sceneBaselineId
    );
    if (unread === 0) continue;

    // Guard on personaId != null (#2166 review fold-in): countUnread can't
    // exclude the viewer's own authored interactions without a personaId, so
    // before the roster loads (personaId still null) a session's own echoed
    // whisper would otherwise count as unread and get misattributed to
    // direct. Route it to ambient instead until personaId resolves.
    if (personaId == null) {
      ambient = true;
      continue;
    }

    if (key.startsWith('whisper:')) {
      direct += unread;
      continue;
    }

    // Same threshold rule, applied to just the rows that name this persona --
    // `countUnread` keyed on the same thread key, so the two counts are directly
    // comparable and whatever is left over is what this persona was not named in.
    const directUnread = countUnread(
      threadInteractions.filter((i) => i.target_persona_ids.includes(personaId)),
      key,
      session.threadLastSeen,
      personaId,
      session.sceneBaselineId
    );
    direct += directUnread;
    if (directUnread < unread) {
      ambient = true;
    }
  }

  return { direct, ambient };
}

/**
 * The badge for one character (#3774): the server's account-wide baseline
 * (`MyRosterEntry.unread_direct`/`has_ambient_unread`) plus whatever this tab
 * has seen arrive since, with the server's own `attention_as_of_id` watermark
 * keeping the two from counting the same pose twice (see `sessionAttention`'s
 * `sinceId`). A character with no local session in this tab has no delta at
 * all -- the server value stands alone, which is the fresh-device case #3774
 * exists for.
 *
 * Canonical shared version: GameTopBar's avatar row and GameWindow's
 * puppet-tab row both call this rather than each computing their own
 * combination, so the two can never drift apart.
 */
export function characterAttention(
  char: MyRosterEntry | undefined,
  session: Session | undefined,
  options?: AttentionOptions
): SessionAttention {
  const serverDirect = char?.unread_direct ?? 0;
  const serverAmbient = char?.has_ambient_unread ?? false;
  if (!session) {
    return { direct: serverDirect, ambient: serverAmbient };
  }
  const delta = sessionAttention(
    session,
    actingPersonaId(char),
    char?.attention_as_of_id ?? 0,
    options
  );
  return { direct: serverDirect + delta.direct, ambient: serverAmbient || delta.ambient };
}

/**
 * The "new" pill on each chip (#3856): how many unread interactions sit under a
 * chip that is on and set to wake, keyed by chip id; chips with nothing new are
 * absent. Unread follows the same rule as `countUnread` (past the thread's
 * last-seen id, or the scene baseline when the thread has none; never the
 * viewer's own rows), applied per row rather than per thread so the count can
 * be split by kind. Dismissed rows never count.
 */
function chipOwners(chips: readonly FeedChip[]): Map<FeedKind, FeedChip> {
  const owners = new Map<FeedKind, FeedChip>();
  for (const chip of chips) {
    if (!chip.on || !chip.wake) continue;
    for (const kind of chip.kinds) owners.set(kind, chip);
  }
  return owners;
}

function isUnreadChipInteraction(
  interaction: ReturnType<typeof wsPayloadToInteraction>,
  session: Session,
  personaId: number | null,
  dismissed: ReadonlySet<string> | undefined,
  owners: Map<FeedKind, FeedChip>
): FeedChip | null {
  if (dismissed?.has(feedItemKey('interaction', interaction.id))) return null;
  if (personaId != null && interaction.persona.id === personaId) return null;
  const chip = owners.get(classifyInteraction(interaction.mode));
  if (!chip) return null;
  const threshold = session.threadLastSeen[getThreadKey(interaction)] ?? session.sceneBaselineId;
  if (threshold === undefined || threshold === null || Number(interaction.id) <= threshold)
    return null;
  return chip;
}

export function chipUnread(
  session: Session,
  personaId: number | null,
  chips: readonly FeedChip[],
  dismissed?: ReadonlySet<string>
): Record<string, number> {
  const counts: Record<string, number> = {};
  const owners = chipOwners(chips);
  if (owners.size === 0) return counts;
  for (const payload of session.sceneInteractions) {
    const interaction = wsPayloadToInteraction(payload);
    const chip = isUnreadChipInteraction(interaction, session, personaId, dismissed, owners);
    if (chip) counts[chip.id] = (counts[chip.id] ?? 0) + 1;
  }
  return counts;
}

import type { Session } from '@/store/gameSlice';
import type { Interaction } from '@/scenes/types';
import { getThreadKey, countUnread } from '@/scenes/hooks/useThreading';
import { wsPayloadToInteraction } from '@/scenes/hooks/useSceneInteractions';

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
 */
export function sessionAttention(session: Session, personaId: number | null): SessionAttention {
  const interactions: Interaction[] = session.sceneInteractions.map(wsPayloadToInteraction);
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

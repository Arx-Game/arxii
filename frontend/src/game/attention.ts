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
 * targets this character) plus `target:*` threads whose key includes
 * `personaId` (an @-target/duel-challenge/consent-request aimed at this
 * persona specifically). `countUnread` already excludes the viewer's own
 * authored interactions, so a thread containing only this persona's own poses
 * contributes to neither tier. Both require `personaId != null` — until the
 * roster resolves it, `countUnread` can't exclude the session's own authored
 * messages, so whisper/target unread routes to `ambient` instead (avoids a
 * pre-roster-load flicker where a session's own echoed whisper reads as
 * direct).
 *
 * `ambient` = true when any other thread (room/place scroll, or a `target:*`
 * thread NOT aimed at this persona) has unread, or the legacy `session.unread`
 * scalar (pre-#2156 sessions / non-interaction game messages) is nonzero.
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

    const isWhisper = key.startsWith('whisper:');
    const isTargetedAtMe = key.startsWith('target:') && targetIncludes(key, personaId);
    // Guard on personaId != null (#2166 review fold-in): countUnread can't
    // exclude the viewer's own authored interactions without a personaId, so
    // before the roster loads (personaId still null) a session's own echoed
    // whisper would otherwise count as unread and get misattributed to
    // direct. Route it to ambient instead until personaId resolves.
    if (personaId != null && (isWhisper || isTargetedAtMe)) {
      direct += unread;
    } else {
      ambient = true;
    }
  }

  return { direct, ambient };
}

function targetIncludes(threadKey: string, personaId: number | null): boolean {
  if (personaId == null) return false;
  const ids = threadKey.slice('target:'.length).split(',').map(Number);
  return ids.includes(personaId);
}

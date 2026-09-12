import type { Interaction } from './types';

/**
 * The viewer's current drafting venue (#3787 decision 3) — the same
 * room-vs-Place shape the composer already tracks (`isAtPlace`/
 * `currentPlaceId` on `CommandInput.tsx`/`GamePage.tsx`), reused here rather
 * than invented fresh so the reader's pre-emptive check and the composer's
 * own check read one shape.
 */
export interface ViewerVenue {
  isAtPlace: boolean;
  currentPlaceId?: number | null;
  /** Human-readable current place name, for the refusal's hint text only. */
  currentPlaceName?: string | null;
}

export interface ReplyRefusal {
  reachable: boolean;
  /** The bold refusal sentence (demo Screen 3's `.refusal strong`). */
  reason?: string;
  /** The quieter follow-on line naming where to go instead (`.refusal .fix`). */
  hint?: string;
}

const REACHABLE: ReplyRefusal = { reachable: true };

/**
 * Mirrors the ONE ratified holder-mismatch copy in
 * `world.scenes.thread_services._holder_mismatch` (#3787 decision 3, "you can
 * only name or answer someone in a venue where they are available"): a
 * Place-held draft (a table-talk aside) answering a Scene-held target (a
 * room-wide pose, or a combat OUTCOME) is refused, in advance, with the same
 * wording the backend uses for the same mismatch on submit.
 *
 * Every OTHER holder combination (a differing Place, a whisper party
 * mismatch, a room-heard target answered from the room, ...) has no ratified
 * copy server-side either (`thread_services.py`'s own comment: "there is no
 * ratified copy for them yet") — this stays permissive (`reachable: true`)
 * for those rather than inventing wording, and the existing submit-time
 * refusal (the rejected-draft banner, carrying the server's own `hint`)
 * still catches them.
 */
export function replyReachability(
  target: Pick<Interaction, 'place' | 'mode'>,
  venue: ViewerVenue
): ReplyRefusal {
  if (venue.isAtPlace && target.place == null && target.mode !== 'whisper') {
    const placeName = venue.currentPlaceName || 'this place';
    return {
      reachable: false,
      reason: 'Answering the fight means speaking to the room.',
      hint: `Leave ${placeName} to answer this. Your draft is kept.`,
    };
  }
  return REACHABLE;
}

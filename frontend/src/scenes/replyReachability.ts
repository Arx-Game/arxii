import type { Interaction } from './types';

/**
 * The viewer's current drafting venue (#3787 decision 3) -- the same
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
 * Mirrors `world.scenes.thread_services`' holder-mismatch rule (#3787
 * decision 3, corrected #3811 / ADR-0293): a Place declutters room chat, it
 * does not isolate its occupants from it, so a player seated at a table can
 * still answer a Scene-held target (a room-wide pose, or a combat OUTCOME) --
 * they already saw it. There is currently no ratified pre-emptive refusal
 * case at all: every holder combination stays permissive here
 * (`reachable: true`), and the one direction the backend still refuses (a
 * room-drafted reply reaching table talk it was never able to see) has no
 * ratified copy either, so the existing submit-time refusal path (the
 * rejected-draft banner, carrying the server's own `hint`) is what catches
 * it.
 */
export function replyReachability(
  _target: Pick<Interaction, 'place' | 'mode'>,
  _venue: ViewerVenue
): ReplyRefusal {
  return REACHABLE;
}

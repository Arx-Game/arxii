/**
 * What kind of line a feed entry is (#3856).
 *
 * The web client shows one feed. Every entry in it, whether a structured
 * interaction (a pose, a say) or a typed text frame (a look result, an item
 * line, an error, an arrival), carries one of these kinds so the filter chips
 * can sort them. The union is closed on purpose: a chip lists kinds, a
 * preference file stores them, so a new kind is a deliberate addition here
 * and in the chip defaults, never an ad hoc string.
 */
export const FEED_KINDS = [
  'pose',
  'say',
  'emit',
  'whisper',
  'action',
  'arrive',
  'move',
  'ambience',
  'vision',
  'look',
  'item',
  'error',
  'system',
] as const;

export type FeedKind = (typeof FEED_KINDS)[number];

const INTERACTION_KINDS = new Set<FeedKind>(['pose', 'say', 'emit', 'whisper', 'action']);

/** The kind of a structured interaction, from its `mode`. An unknown mode reads as a pose. */
export function classifyInteraction(mode: string): FeedKind {
  return INTERACTION_KINDS.has(mode as FeedKind) ? (mode as FeedKind) : 'pose';
}

/**
 * The kind of a `text` frame, from its `kwargs.type`.
 *
 * The server sends the type through Evennia's tuple form
 * (`msg((text, {"type": kind}))`), whose dict becomes the frame's kwargs:
 * commands send `look`, `item` and `error` (`ArxCommand.send_result`), Evennia's
 * own movement announcements send `move` for a departure and, through our
 * `Character.announce_move_to`, `arrive` for an arrival, and the narrative
 * service sends `narrative` or `gemit`, both ambience here. A narrative frame
 * also carries its `category` (#3779); the `visions` category is the one lane
 * with its own kind, `vision`, so the treatment reserved for a god's message
 * reaches the feed at the delivery moment. A frame with no type, or one this
 * client does not know, is a plain line it cannot place: `system`.
 */
export function classifyText(wireType: unknown, category?: unknown): FeedKind {
  switch (wireType) {
    case 'look':
    case 'item':
    case 'error':
    case 'move':
    case 'arrive':
      return wireType;
    case 'narrative':
      return category === 'visions' ? 'vision' : 'ambience';
    case 'gemit':
      return 'ambience';
    default:
      return 'system';
  }
}
